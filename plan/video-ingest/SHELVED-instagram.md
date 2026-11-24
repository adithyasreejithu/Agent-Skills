# Instagram ingest (SHELVED)

**Superseded on 2026-10-22 by `plan/reels/PLAN.md`**: a headless browser on public profiles of a vetted
creator list replaces the Graph API, with the manual link inbox kept as a second way in.

Status: shelved on 2026-10-20 by decision. The user has a personal account, so the official Graph API is not
usable without converting to Creator/Business, and it often withholds video URLs. The agreed fallback when this
is revisited: manual link inbox (`ingest/inbox/`) feeding the same queue, with yt-dlp on the permalink as a
best-effort fetch (cookies likely needed, reels have no captions so a transcription backend is required, and
downloading is a terms-of-service grey area). Possible later add-on: Claude in Chrome collecting reel links
from followed profiles into the inbox. Notes from the earlier research follow.

## Graph API research notes

Verified against Meta's Business Discovery doc; the rest comes from third-party 2026 guides and must be checked
against developers.facebook.com before building.

## What the official API can and cannot do
It is built for businesses managing their own accounts. It is **not** a way to follow arbitrary people.

| Capability | Works for | Notes |
|---|---|---|
| Read your own media (`/{ig-user-id}/media`) | Your own Business/Creator account | Reels, videos, captions, permalinks, `media_url` |
| **Business Discovery** | Other *professional* (Business/Creator) accounts, by username | The only official way to read someone else's public posts. Returns profile counts and their `media` edge (caption, permalink, timestamp, like/comment counts, `media_url`) |
| Hashtag search | Public posts with a hashtag | Facebook Login only; about 30 unique hashtags per 7 days per account; recent/top media, no video URLs for many results |
| Mentions / tags | Posts that mention or tag your account | Needs your account to be tagged |
| Publishing, comments, insights | Your own account | Not relevant here |

## Business Discovery, specifically (what we would use)
```
GET https://graph.facebook.com/v26.0/{your-ig-user-id}
    ?fields=business_discovery.username(TARGET){username,media_count,
        media.limit(25){id,caption,media_type,media_product_type,permalink,timestamp,media_url}}
    &access_token={token}
```
- Lists the target's recent media, so it works as the Instagram equivalent of the RSS poll. Poll it, diff on media id.
- **Target must be a professional account** and not age-gated. Personal accounts and most private accounts: no data.
- **`media_url` is withheld** for videos with licensed/library audio (a large share of reels), for reels whose owner
  disabled downloads, and for copyright-flagged media. The permalink and caption still come back.
- You **cannot fetch an individual media object** returned this way; you only get it through the nested query.
- Meta's doc does not state rate limits or pagination for this endpoint; treat it as app-level rate limited and
  cache aggressively.

## What it takes to get set up
1. An Instagram **Business or Creator** account for *you*, linked to a Facebook Page (Facebook Login path).
2. A Meta developer account and an app (type Business) with the Instagram product added.
3. Permissions for reading your own media plus Business Discovery (`instagram_basic`, `pages_show_list`,
   `instagram_manage_insights`-class; exact set per the endpoint reference).
4. **Development mode** works immediately for accounts with a role on your app, so for a personal tool you can run
   in dev mode and never go through **App Review**. App Review / Advanced Access is only needed if other people's
   accounts authorize your app.
5. A long-lived user token (about 60 days) that must be refreshed, stored in `~/.config/` env, never in the repo.
6. The "Instagram Login" product (no Facebook Page) is simpler to set up but does **not** include Business
   Discovery or hashtag search, so it is not enough for discovery.

## Reality check for this project
- Even when Business Discovery returns a reel, there is often **no downloadable `media_url`**, and Meta's terms
  do not grant a right to download other people's content. The permalink is always there, though.
- `/watch` runs through yt-dlp, which can often fetch a public reel from its permalink (sometimes needing cookies).
  That is outside the official API and can break or violate terms, so keep it as a clearly separate, optional step.
- Safest official-only use: **discovery via Business Discovery, then you review the captions/permalinks**; for videos
  you want summarized, either yt-dlp the permalink yourself or use your own accounts' content where `media_url` works.

## Instagram adapter design (phase 4)
- Same queue table with `platform='instagram'`, `video_id` = media id, `url` = permalink.
- `sources.yaml` entry: `kind: instagram, username: someaccount`. Poll every few hours (reels are slower-moving).
- Items land `queued` with `fetch_mode: permalink`; the skill tries `/watch` on the permalink and, if yt-dlp
  fails, marks `needs_manual` with the permalink and caption so you can handle it.
- Skip when `media_type` is not VIDEO / `media_product_type` is not REELS or FEED video.
- Isolated behind one adapter interface (`discover(source) -> list[Candidate]`) shared with YouTube, so Instagram
  breaking never affects YouTube polling.

## Instagram open questions
1. Which accounts do you want to follow, and are they Business/Creator accounts? Personal ones cannot be read
   through the official API at all.
2. Are you willing to set up a Meta app and a Facebook Page, or is a manual "paste the reel URL" inbox enough?
3. Is yt-dlp-on-permalink acceptable as a best-effort fetch step? [yes, optional, off by default]

## Sources
- Meta: Business Discovery, Instagram Platform (Facebook Login) docs
- Third-party 2026 guides (unverified details on limits): getphyllo.com/post/instagram-api-guide,
  bundle.social/blog/instagram-graph-api, zernio.com/blog/instagram-api
