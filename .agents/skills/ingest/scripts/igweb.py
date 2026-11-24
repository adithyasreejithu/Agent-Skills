#!/usr/bin/env python3
"""Instagram access for the reels pipeline: a browser for profile pages, yt-dlp for one reel's details.

Two modes:
- Logged out: a public profile's reels tab shows its latest 12 reels and scrolling loads no more (checked
  2026-10-22). The page embeds each reel's code, play count and pinned flag but not its date, so the date and
  caption come from yt-dlp, once per new reel.
- Logged in (a burner account, after `run.py reels login`): the same reels tab keeps loading as it scrolls, and
  the API answers carry each reel's date, caption and length, so no yt-dlp lookup is needed. The session lives
  in a persistent browser profile outside the repo; the password is typed by the user and never stored.

The logged-in mode is built to look and behave like one person browsing: one profile, the user agent of the
browser the user logged in with, read-only visits to the vetted profiles only, slow irregular scrolling, a cap on
scrolls, and a full stop at the first sign of a challenge, a rate limit or a login redirect.
Playwright is imported lazily: nothing else in ingest needs it.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from store import iso, parse_ts
from urls import REEL_CODE, reel_url

PROFILE_URL = 'https://www.instagram.com/{username}/reels/'
LOGIN_URL = 'https://www.instagram.com/accounts/login/'
SESSION_FILE = 'ig-session.json'        # in the profile folder: user agent, when the login was saved
PAGE_TIMEOUT_MS = 45_000
SETTLE_S = (3.5, 6.0)
SCROLL_PAUSE_S = (2.5, 6.0)             # between scrolls, logged in
SCROLL_PX = (1800, 3600)
GAP_S = (4.0, 9.0)                      # between profiles
DAILY_SCROLLS = 4                       # per profile on a normal poll; the backfill passes more
STALL_SCROLLS = 2                       # stop when this many scrolls in a row bring nothing new
OLD_IN_A_ROW = 3
LOGIN_WAIT_S = 6 * 60
META_TIMEOUT_S = 90
LAUNCH_ARGS = ['--disable-blink-features=AutomationControlled']
# Public shortcodes are 11 characters (older ones 10). The length floor keeps out other "code" values, e.g. en_US.
_CODE = re.compile(r'"code":"([A-Za-z0-9_-]{10,14})"')
_ANCHOR = re.compile(r'/reel/(' + REEL_CODE.pattern + r')/')
BLOCK_TEXT = ('checkpoint_required', 'feedback_required', 'challenge_required', 'Please wait a few minutes',
              'Try Again Later', 'We restrict certain activity', 'suspended your account', 'confirm it\'s you')
BLOCK_URLS = ('/challenge/', '/accounts/suspended', '/accounts/disabled', '/checkpoint/')


class IgError(Exception):
    """A temporary or unexplained failure; try again on the next poll."""


class LoginWall(IgError):
    pass


class Blocked(IgError):
    """Instagram pushed back (challenge, rate limit, restriction). Stop everything and cool down."""


class NotFound(IgError):
    pass


class Unavailable(IgError):
    """This one reel is gone or private."""


@dataclass
class Candidate:
    code: str
    username: str
    pinned: bool = False
    views: int | None = None
    taken_at: str | None = None
    caption: str | None = None
    duration_s: float | None = None
    via: str = 'dom'

    @property
    def url(self) -> str:
        return reel_url(self.code)


@dataclass
class Profile:
    username: str
    candidates: list[Candidate] = field(default_factory=list)
    final_url: str = ''
    scrolls: int = 0


# ---- parsing (pure, tested on fixtures) --------------------------------------
def _field_near(before: str, after: str, pattern: str):
    """The field value closest to a code: last match before it, else first match after it."""
    found = re.findall(pattern, before)
    if found:
        return found[-1]
    match = re.search(pattern, after)
    return match.group(1) if match else None


def _unescape(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw


def parse_media(text: str) -> dict[str, dict]:
    """Every reel object in a page or JSON body: code -> {pinned, views, taken_at, caption, duration_s}.

    Instagram's objects are large and their key order varies, so each field is taken from the stretch between
    the previous and the next `"code"` and the nearest occurrence wins.
    """
    matches = list(_CODE.finditer(text))
    out: dict[str, dict] = {}
    for i, match in enumerate(matches):
        before = text[matches[i - 1].end() if i else max(0, match.start() - 4000):match.start()]
        after = text[match.end():matches[i + 1].start() if i + 1 < len(matches) else match.end() + 4000]
        if 'clips' not in before + after and '"is_video":true' not in before + after and '"media_type":2' not in before + after:
            continue                        # some other kind of "code" (a post, an error code)
        pinned = _field_near(before, after, r'"clips_tab_pinned_user_ids":\[([^\]]*)\]')
        views = _field_near(before, after, r'"(?:play_count|video_view_count|view_count)":(\d+)')
        taken = _field_near(before, after, r'"(?:taken_at|taken_at_timestamp)":(\d{9,11})')
        duration = _field_near(before, after, r'"video_duration":([\d.]+)')
        caption = _field_near(before, after, r'"caption":\{[^{}]*?"text":"((?:[^"\\]|\\.)*)"')
        entry = out.setdefault(match.group(1), {})
        entry.setdefault('pinned', bool(pinned and pinned.strip()))
        if views and 'views' not in entry:
            entry['views'] = int(views)
        if taken and 'taken_at' not in entry:
            entry['taken_at'] = iso(datetime.fromtimestamp(int(taken), timezone.utc))
        if duration and 'duration_s' not in entry:
            entry['duration_s'] = float(duration)
        if caption is not None and 'caption' not in entry:
            entry['caption'] = _unescape(caption)
    return out


def block_signal(text: str) -> str | None:
    """The first sign in a page or API answer that Instagram is pushing back, or None."""
    for marker in BLOCK_TEXT:
        if marker in text:
            return marker
    return None


def page_problem(final_url: str, html: str, logged_in: bool = False) -> IgError | None:
    if any(part in final_url for part in BLOCK_URLS):
        return Blocked(f'Instagram showed a check page ({final_url})')
    if '/accounts/login' in final_url:
        if logged_in:
            return Blocked('the saved login was not accepted (sent to the login page); run `reels login` again')
        return LoginWall(f'Instagram sent the browser to a login page ({final_url})')
    signal = block_signal(html)
    if signal:
        return Blocked(f'Instagram says: {signal}')
    if "Sorry, this page isn't available" in html or 'Page not found' in html[:5000]:
        return NotFound('profile not found or not public')
    return None


def merge_media(bodies) -> dict[str, dict]:
    media: dict[str, dict] = {}
    for body in bodies:
        for code, values in parse_media(body).items():
            known = media.setdefault(code, {})
            known.update({k: v for k, v in values.items() if k not in known})
    return media


def codes_from_anchors(anchors: list[str]) -> list[str]:
    codes: list[str] = []
    for href in anchors:
        match = _ANCHOR.search(href or '')
        if match and match.group(1) not in codes:
            codes.append(match.group(1))
    return codes


def keep_order(seen: list[str], more: list[str]) -> list[str]:
    """`seen` plus any links in `more` it lacks, in first-seen order."""
    return seen + [href for href in dict.fromkeys(more) if href not in set(seen)]


def candidates_from_page(username: str, final_url: str, html: str, anchors: list[str],
                         extra_bodies: list[str] = (), logged_in: bool = False,
                         visible: str | None = None) -> list[Candidate]:
    """Order and membership come from the reel links on the page (newest first); details from the embedded JSON.
    `visible` is the page's rendered text; warnings are looked for there, since script bundles may quote them."""
    problem = page_problem(final_url, html if visible is None else visible, logged_in)
    if problem:
        raise problem
    media = merge_media((html, *extra_bodies))
    codes, via = codes_from_anchors(anchors), 'dom'
    if not codes:                       # the link markup changed: fall back to the embedded objects
        codes, via = list(media), 'json'
    if not codes and ('Log in' in html or 'log in' in html) and '"code":"' not in html:
        raise LoginWall('the profile page showed no reels, only a login prompt')
    return [Candidate(code=c, username=username, via=via if c not in media else 'json', **media.get(c, {}))
            for c in codes]


def past_horizon(found: list[Candidate], since: datetime | None) -> bool:
    """True once OLD_IN_A_ROW non-pinned reels in a row (newest first) are older than `since`."""
    if since is None:
        return False
    run = 0
    for cand in found:
        if cand.pinned:
            continue
        taken = parse_ts(cand.taken_at)
        if taken is None:
            run = 0
            continue
        run = run + 1 if taken < since else 0
        if run >= OLD_IN_A_ROW:
            return True
    return False


def fill_meta(found: list[Candidate], looked: dict[str, dict]) -> list[Candidate]:
    """Give candidates the details looked up for them (yt-dlp) where the page had none."""
    for cand in found:
        meta = looked.get(cand.code) or {}
        cand.taken_at = cand.taken_at or meta.get('taken_at')
        cand.caption = cand.caption if cand.caption is not None else meta.get('caption')
        cand.duration_s = cand.duration_s or meta.get('duration_s')
    return found


def last_unchecked(found: list[Candidate], looked: dict[str, dict]) -> Candidate | None:
    """The oldest loaded reel (the last non-pinned one) when its date is unknown and not looked up yet."""
    edge = next((c for c in reversed(found) if not c.pinned), None)
    return edge if edge and not edge.taken_at and edge.code not in looked else None


def edge_older(found: list[Candidate], since: datetime | None) -> bool:
    """True when the oldest loaded non-pinned reel is older than `since`: the grid already reaches back far enough."""
    edge = next((c for c in reversed(found) if not c.pinned), None)
    taken = parse_ts(edge.taken_at) if edge else None
    return bool(since and taken and taken < since)


def meta_from_ytdlp(info: dict) -> dict:
    """yt-dlp's -J output for one reel -> the fields the queue needs."""
    stamp = info.get('timestamp')
    taken = iso(datetime.fromtimestamp(int(stamp), timezone.utc)) if isinstance(stamp, (int, float)) else None
    if not taken and info.get('upload_date'):
        d = str(info['upload_date'])
        taken = f'{d[:4]}-{d[4:6]}-{d[6:8]}T00:00:00Z'
    duration = info.get('duration')
    if not duration:
        durations = [f.get('duration') for f in info.get('formats') or [] if f.get('duration')]
        duration = max(durations) if durations else None
    return {'taken_at': taken, 'caption': info.get('description') or info.get('title') or '',
            'duration_s': float(duration) if duration else None,
            'username': (info.get('channel') or info.get('uploader_id') or '').lower() or None,
            'creator_name': info.get('uploader')}


# ---- the saved login ---------------------------------------------------------------
def read_session(profile_dir: Path | None) -> dict | None:
    """The saved login's details, or None when there is no usable login."""
    if not profile_dir:
        return None
    try:
        data = json.loads((Path(profile_dir) / SESSION_FILE).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return data if data.get('user_agent') else None


def login(profile_dir: Path, *, wait_s: int = LOGIN_WAIT_S, say=print) -> dict:
    """Open a visible browser on the login page and wait for the user to log in by hand. The password goes from
    the user's keyboard to Instagram; this code only keeps the browser profile and the browser's user agent."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise IgError('Playwright is not installed: run `uv add playwright` and '
                      '`python -m playwright install chromium`') from None
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(str(profile_dir), headless=False, args=LAUNCH_ARGS,
                                                        viewport={'width': 1280, 'height': 900})
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(LOGIN_URL, wait_until='domcontentloaded', timeout=PAGE_TIMEOUT_MS)
            say('A browser window is open on the Instagram login page. Log in with the burner account there '
                '(answer any 2FA or "save login info" prompt). This waits up to '
                f'{wait_s // 60} minutes and closes the window by itself once you are in.')
            deadline = time.monotonic() + wait_s
            while time.monotonic() < deadline:
                if any(c['name'] == 'sessionid' and c['value'] for c in context.cookies('https://www.instagram.com')):
                    break
                page.wait_for_timeout(2000)
            else:
                raise IgError('no login within the time limit; nothing was saved')
            page.wait_for_timeout(4000)        # let Instagram finish its post-login redirects and cookies
            user_agent = page.evaluate('navigator.userAgent')
            account = next((c['value'] for c in context.cookies('https://www.instagram.com')
                            if c['name'] == 'ds_user_id'), None)
        finally:
            context.close()
    session = {'user_agent': user_agent, 'saved_at': iso(datetime.now(timezone.utc)), 'account_id': account}
    (profile_dir / SESSION_FILE).write_text(json.dumps(session, indent=2), encoding='utf-8')
    return session


# ---- the live browser -----------------------------------------------------------------
def _ytdlp() -> str:
    """The venv's yt-dlp first: a scheduled task has no venv activated."""
    local = Path(sys.executable).parent / ('yt-dlp.exe' if sys.platform == 'win32' else 'yt-dlp')
    return str(local) if local.is_file() else (shutil.which('yt-dlp') or 'yt-dlp')


class IgWeb:
    """One browser for a whole poll. Use as a context manager.

    With `profile_dir` holding a saved login the browser runs logged in (persistent profile, the saved user
    agent); without it, logged out in a throwaway context.
    """

    def __init__(self, *, headless: bool = True, profile_dir: Path | None = None, debug_dir: Path | None = None,
                 sleep=time.sleep):
        self.headless = headless
        self.profile_dir = Path(profile_dir) if profile_dir else None
        self.session = read_session(self.profile_dir)
        self.debug_dir = debug_dir
        self.sleep = sleep
        self._pw = self._browser = self._context = None
        self._visited = 0

    @property
    def logged_in(self) -> bool:
        return self.session is not None

    def __enter__(self) -> 'IgWeb':
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _pause(self, span: tuple[float, float]) -> None:
        self.sleep(random.uniform(*span))

    def _start(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise IgError('Playwright is not installed: run `uv add playwright` and '
                          '`python -m playwright install chromium`') from None
        self._pw = sync_playwright().start()
        options = {'viewport': {'width': 1280, 'height': 900}}
        if self.logged_in:
            # Same profile and user agent as the window the user logged in with, so it looks like one device.
            self._context = self._pw.chromium.launch_persistent_context(
                str(self.profile_dir), headless=self.headless, args=LAUNCH_ARGS,
                user_agent=self.session['user_agent'], **options)
        else:
            self._browser = self._pw.chromium.launch(headless=self.headless, args=LAUNCH_ARGS)
            self._context = self._browser.new_context(locale='en-US', **options)

    def close(self) -> None:
        for thing, method in ((self._context, 'close'), (self._browser, 'close'), (self._pw, 'stop')):
            if thing is not None:
                try:
                    getattr(thing, method)()
                except Exception:
                    pass
        self._pw = self._browser = self._context = None

    def profile(self, username: str, since: datetime | None = None, max_scrolls: int | None = None) -> Profile:
        """The creator's reels, newest first. Logged in, it scrolls until reels older than `since` show up (or
        `max_scrolls`, or nothing new loads); logged out, one look is all Instagram allows."""
        if self._visited:
            self._pause(GAP_S)
        self._visited += 1
        self._start()
        page = self._context.new_page()
        bodies: list[str] = []
        looked: dict[str, dict] = {}     # yt-dlp details (logged out) for reels the grid gave no date
        pushback: list[str] = []

        def keep(response):
            if 'www.instagram.com' not in response.url:
                return
            if response.status == 429:
                pushback.append(f'HTTP 429 from {response.url[:80]}')
                return
            kind = response.headers.get('content-type', '')
            if 'json' not in kind and 'javascript' not in kind:   # api/graphql answers as text/javascript
                return
            try:
                body = response.text()
            except Exception:
                return
            signal = block_signal(body[:20000])
            if signal:
                pushback.append(signal)
            elif '"code":"' in body:
                bodies.append(body)

        page.on('response', keep)
        scrolls = 0
        try:
            try:
                page.goto(PROFILE_URL.format(username=username), wait_until='domcontentloaded',
                          timeout=PAGE_TIMEOUT_MS)
                self._pause(SETTLE_S)
                html, visible = page.content(), self._visible(page)
                problem = page_problem(page.url, visible, self.logged_in)
                if problem:
                    self._dump(username, html)
                    raise problem
                limit = (max_scrolls if max_scrolls is not None else DAILY_SCROLLS) if self.logged_in else 1
                seen, stalled = 0, 0
                anchors: list[str] = []          # every reel link seen; the grid drops its top rows as it scrolls
                while scrolls < limit and not pushback:
                    anchors = keep_order(anchors, self._anchors(page))
                    found = fill_meta(candidates_from_page(username, page.url, html, anchors, bodies,
                                                           self.logged_in, visible), looked)
                    if past_horizon(found, since):
                        break
                    edge = last_unchecked(found, looked) if since and self.logged_in else None
                    if edge:                     # the logged-in grid carries no dates: check the oldest one
                        try:
                            looked[edge.code] = self.reel_meta(edge.code)
                        except IgError:
                            looked[edge.code] = {}
                        fill_meta(found, looked)
                    if edge_older(found, since):
                        break
                    stalled = stalled + 1 if len(found) <= seen else 0
                    if stalled >= STALL_SCROLLS:
                        break
                    seen = len(found)
                    page.mouse.wheel(0, random.randint(*SCROLL_PX))
                    scrolls += 1
                    self._pause(SCROLL_PAUSE_S)
                    html, visible = page.content(), self._visible(page)
                final_url, anchors = page.url, keep_order(anchors, self._anchors(page))
            except IgError:
                raise
            except Exception as exc:              # timeouts, navigation errors
                raise IgError(f'{type(exc).__name__}: {str(exc).splitlines()[0][:200]}') from None
            if pushback:
                raise Blocked(f'Instagram pushed back while scrolling @{username}: {pushback[0]}')
            try:
                found = fill_meta(candidates_from_page(username, final_url, html, anchors, bodies,
                                                       self.logged_in, visible), looked)
            except IgError:
                self._dump(username, html)
                raise
            if not found:
                self._dump(username, html)
            return Profile(username, found, final_url, scrolls)
        finally:
            page.close()

    @staticmethod
    def _visible(page) -> str:
        try:
            return page.inner_text('body', timeout=5000)
        except Exception:
            return ''

    @staticmethod
    def _anchors(page) -> list[str]:
        return page.eval_on_selector_all('a[href*="/reel/"]', 'els => els.map(e => e.getAttribute("href"))')

    def _dump(self, username: str, html: str) -> None:
        if self.debug_dir:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            (self.debug_dir / f'{username}.html').write_text(html, encoding='utf-8')

    def reel_meta(self, code: str) -> dict:
        """One reel's details through yt-dlp, always logged out: the burner account is never used for this."""
        cmd = [_ytdlp(), '--skip-download', '--no-playlist', '--no-cookies-from-browser', '-J', '--', reel_url(code)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                  timeout=META_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise IgError(f'yt-dlp timed out on {code}') from None
        except FileNotFoundError:
            raise IgError('yt-dlp is not installed in this environment') from None
        if proc.returncode != 0:
            err = (proc.stderr or '').strip().splitlines()
            tail = err[-1][:200] if err else f'exit {proc.returncode}'
            low = tail.lower()
            if 'not available' in low or 'removed' in low or 'private' in low or '404' in low:
                raise Unavailable(tail)
            if 'login' in low or 'rate' in low or '429' in low:
                raise LoginWall(tail)
            raise IgError(tail)
        try:
            return meta_from_ytdlp(json.loads(proc.stdout))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise IgError(f'unreadable yt-dlp output for {code}: {exc}') from None
