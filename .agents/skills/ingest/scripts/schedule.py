#!/usr/bin/env python3
"""Windows Task Scheduler setup for the weekday-morning ingest run.

  schedule.py print   [--time HH:MM] [--name N] [--project DIR]   show what would be registered; changes nothing
  schedule.py install [same flags] --yes                          register it (without --yes it only prints)
  schedule.py status  [--name N]
  schedule.py remove  [--name N]

The task runs `python run.py tick --log` Monday to Friday from the project folder, only while the user is logged on,
never two at once, catches up after sleep, and is killed after 4 hours. The tick itself stops starting new videos
after 180 minutes. Uses PowerShell's ScheduledTasks cmdlets, so no extra packages.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_NAME = 'IngestVideos'
DEFAULT_TIME = '07:00'
DAYS = 'Monday,Tuesday,Wednesday,Thursday,Friday'
TIME_LIMIT_HOURS = 4


def ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def build_script(name: str, at: str, project: Path, python: str, run_py: Path) -> str:
    if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', at):
        raise ValueError(f'--time must be HH:MM (24-hour), got {at!r}')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
        raise ValueError('--name may only contain letters, digits, _ . -')
    argument = f'"{run_py}" tick --log'
    return '\n'.join([
        f'$action = New-ScheduledTaskAction -Execute {ps_quote(python)} -Argument {ps_quote(argument)} '
        f'-WorkingDirectory {ps_quote(str(project))}',
        f'$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek {DAYS} -At {at}',
        f'$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable '
        f'-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours {TIME_LIMIT_HOURS})',
        '$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive',
        f'Register-ScheduledTask -TaskName {ps_quote(name)} -Action $action -Trigger $trigger -Settings $settings '
        f'-Principal $principal -Description "Poll YouTube channels and write notes (ingest skill), weekdays" -Force | Out-Null',
        f'Write-Output ("registered " + {ps_quote(name)})',
    ])


def powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, encoding='utf-8', errors='replace')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('action', choices=['print', 'install', 'status', 'remove'])
    ap.add_argument('--name', default=DEFAULT_NAME)
    ap.add_argument('--time', default=DEFAULT_TIME, help='24-hour HH:MM, local time (default 07:00)')
    ap.add_argument('--project', default='.', help='folder containing ingest.env (default: current directory)')
    ap.add_argument('--yes', action='store_true', help='actually register the task (install only)')
    args = ap.parse_args(argv)

    if sys.platform != 'win32':
        print('schedule.py targets Windows Task Scheduler. On macOS/Linux use cron or launchd with: '
              'python run.py tick --log  (weekdays, from the project folder)')
        return 2
    run_py = Path(__file__).resolve().with_name('run.py')
    project = Path(args.project).resolve()

    if args.action in ('print', 'install'):
        try:
            script = build_script(args.name, args.time, project, sys.executable, run_py)
        except ValueError as exc:
            print(f'error: {exc}', file=sys.stderr)
            return 2
        print(f'Task      {args.name}\nWhen      Monday to Friday at {args.time}, only while you are logged on\n'
              f'Command   {sys.executable} "{run_py}" tick --log\nStart in  {project}\n'
              f'Limits    one at a time, catches up after sleep, killed after {TIME_LIMIT_HOURS} h\n\n{script}\n')
        if args.action == 'print':
            return 0
        if not args.yes:
            print('Nothing registered. Re-run with --yes to register this task.')
            return 1
        done = powershell(script)
        print((done.stdout or done.stderr).strip())
        return done.returncode
    if args.action == 'status':
        query = (f'$t = Get-ScheduledTask -TaskName {ps_quote(args.name)} -ErrorAction SilentlyContinue; '
                 f'if (-not $t) {{ "not registered"; exit 1 }}; $i = Get-ScheduledTaskInfo -TaskName {ps_quote(args.name)}; '
                 f'"state       " + $t.State; "next run    " + $i.NextRunTime; "last run    " + $i.LastRunTime; '
                 f'"last result " + $i.LastTaskResult')
        done = powershell(query)
        print((done.stdout or done.stderr).strip())
        return done.returncode
    done = powershell(f'Unregister-ScheduledTask -TaskName {ps_quote(args.name)} -Confirm:$false -ErrorAction Stop; '
                      f'"removed {args.name}"')
    print((done.stdout or done.stderr).strip())
    return done.returncode


if __name__ == '__main__':
    sys.exit(main())
