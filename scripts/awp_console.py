"""Terminal console for AWP RP Runtime.

Usage:
  python scripts/awp_console.py --session sess-xxx
  python scripts/awp_console.py --session sess-xxx transcript
  python scripts/awp_console.py --session sess-xxx stream "你好"
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


GREEN = "\033[92m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def _url(base: str, path: str) -> str:
    return base.rstrip("/") + path


def _post_json(base: str, path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _url(base, path),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    return json.loads(body).get("data", {})


def _print_json(data: object, ok: bool = True) -> None:
    color = GREEN if ok else RED
    print(color + json.dumps(data, ensure_ascii=False, indent=2, default=str) + RESET)


def run_command(base: str, session_id: str, command: str) -> None:
    result = _post_json(
        base,
        "/awp/api/v1/console/command",
        {"session_id": session_id, "command": command},
    )
    ok = bool(result.get("ok", False))
    data = result.get("data", {})
    if isinstance(data, dict) and isinstance(data.get("text"), str):
        print((GREEN if ok else RED) + data["text"] + RESET)
    else:
        output = result.get("output", "")
        if output:
            print((GREEN if ok else RED) + str(output) + RESET)
        _print_json(data, ok=ok)


def _iter_sse(response):
    buffer = ""
    while True:
        chunk = response.read(1)
        if not chunk:
            break
        buffer += chunk.decode("utf-8", errors="replace")
        if buffer.endswith("\n\n"):
            yield buffer.strip()
            buffer = ""
    if buffer.strip():
        yield buffer.strip()


def stream_turn(base: str, session_id: str, text: str, mode: str) -> None:
    query = f"?mode={mode}" if mode else ""
    request = urllib.request.Request(
        _url(base, f"/awp/api/v1/sessions/{session_id}/turn/stream{query}"),
        data=json.dumps({"player_input": text}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        for block in _iter_sse(response):
            print(GREEN + block + RESET)


def repl(base: str, session_id: str, mode: str) -> None:
    print(GREEN + "AWP runtime console. Type help, transcript, send \"...\", stream \"...\", or exit." + RESET)
    while True:
        try:
            command = input(GREEN + "awp> " + RESET).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not command:
            continue
        if command.lower() in {"exit", "quit"}:
            return
        if command.lower() == "clear":
            print("\033c", end="")
            continue
        if command.startswith("stream "):
            stream_turn(base, session_id, command[len("stream "):].strip().strip("\"'"), mode)
            continue
        try:
            run_command(base, session_id, command)
        except Exception as exc:
            print(RED + str(exc) + RESET)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="*", help="Command to run. Omit for REPL.")
    parser.add_argument("--base", default="http://127.0.0.1:8188")
    parser.add_argument("--session", default="")
    parser.add_argument("--mode", default="python")
    args = parser.parse_args(argv)

    command = " ".join(args.command).strip()
    if command.startswith("stream "):
        if not args.session:
            raise SystemExit("--session is required for stream")
        stream_turn(args.base, args.session, command[len("stream "):].strip().strip("\"'"), args.mode)
        return 0
    if command:
        run_command(args.base, args.session, command)
        return 0
    repl(args.base, args.session, args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
