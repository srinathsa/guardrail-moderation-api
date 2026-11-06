"""
Pulls real posts/comments from Reddit and runs each one through the
Guardrail Moderation API automatically.

Setup (free, ~2 minutes):
  1. Go to https://www.reddit.com/prefs/apps
  2. Click "create app" / "create another app"
  3. Choose type: "script"
  4. Name: anything (e.g. "guardrail-bridge"), redirect uri: http://localhost:8000
  5. After creating, note the client ID (under the app name) and client secret
  6. Add to your .env file:
       REDDIT_CLIENT_ID=your_client_id
       REDDIT_CLIENT_SECRET=your_client_secret
       REDDIT_USER_AGENT=guardrail-bridge by u/your_username

Install the one extra dependency:
  pip install praw

Usage examples:
  # Check the 20 newest posts in r/test, one-time batch
  python integrations/reddit_moderator.py --subreddit test --limit 20

  # Check posts AND their top-level comments
  python integrations/reddit_moderator.py --subreddit test --limit 10 --include-comments

  # Continuously watch a subreddit's new comments in real time (Ctrl+C to stop)
  python integrations/reddit_moderator.py --subreddit test --stream
"""
import argparse
import os
import sys
import time

import praw
import requests


def load_dotenv_if_present():
    """Minimal .env loader so this script works standalone without extra deps."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def get_reddit_client() -> praw.Reddit:
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "guardrail-bridge")

    if not client_id or not client_secret:
        print(
            "ERROR: REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set "
            "(in your .env file or as environment variables).\n"
            "Get free credentials at https://www.reddit.com/prefs/apps",
            file=sys.stderr,
        )
        sys.exit(1)

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


def moderate_text(api_base: str, api_key: str, text: str) -> dict:
    """Calls this project's own POST /moderate/text endpoint."""
    resp = requests.post(
        f"{api_base}/moderate/text",
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        json={"text": text[:20000]},  # matches the API's max length
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def print_result(source_label: str, text_preview: str, result: dict):
    icon = {"allow": "✅", "flag": "🟡", "block": "🔴"}.get(result["decision"], "?")
    print(f"{icon} [{result['decision'].upper()}] {source_label}")
    print(f"    text: {text_preview[:100]!r}")
    if result["reasons"]:
        print(f"    reasons: {'; '.join(result['reasons'])}")
    print()


def run_batch(reddit, args):
    subreddit = reddit.subreddit(args.subreddit)
    print(f"Fetching {args.limit} newest posts from r/{args.subreddit}...\n")

    for post in subreddit.new(limit=args.limit):
        combined_text = f"{post.title}\n{post.selftext or ''}".strip()
        if not combined_text:
            continue
        try:
            result = moderate_text(args.api_base, args.api_key, combined_text)
            print_result(f"post {post.id} (u/{post.author})", combined_text, result)
        except requests.RequestException as e:
            print(f"⚠️  Failed to moderate post {post.id}: {e}\n")

        if args.include_comments:
            post.comments.replace_more(limit=0)
            for comment in post.comments.list()[: args.comment_limit]:
                if not comment.body or comment.body in ("[deleted]", "[removed]"):
                    continue
                try:
                    result = moderate_text(args.api_base, args.api_key, comment.body)
                    print_result(f"comment {comment.id} (u/{comment.author})", comment.body, result)
                except requests.RequestException as e:
                    print(f"⚠️  Failed to moderate comment {comment.id}: {e}\n")


def run_stream(reddit, args):
    subreddit = reddit.subreddit(args.subreddit)
    print(f"Streaming new comments from r/{args.subreddit} in real time (Ctrl+C to stop)...\n")
    try:
        for comment in subreddit.stream.comments(skip_existing=True):
            if not comment.body or comment.body in ("[deleted]", "[removed]"):
                continue
            try:
                result = moderate_text(args.api_base, args.api_key, comment.body)
                print_result(f"comment {comment.id} (u/{comment.author})", comment.body, result)
            except requests.RequestException as e:
                print(f"⚠️  Failed to moderate comment {comment.id}: {e}\n")
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    load_dotenv_if_present()

    parser = argparse.ArgumentParser(description="Moderate real Reddit content with the Guardrail API")
    parser.add_argument("--subreddit", default="test", help="Subreddit name, without r/ (default: test)")
    parser.add_argument("--limit", type=int, default=10, help="Number of newest posts to check (batch mode)")
    parser.add_argument("--include-comments", action="store_true", help="Also check each post's comments")
    parser.add_argument("--comment-limit", type=int, default=5, help="Max comments per post to check")
    parser.add_argument("--stream", action="store_true", help="Continuously watch new comments instead of a one-time batch")
    parser.add_argument("--api-base", default=os.environ.get("MODERATION_API_BASE", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("API_KEY", "changeme-dev-key"))
    args = parser.parse_args()

    reddit = get_reddit_client()

    if args.stream:
        run_stream(reddit, args)
    else:
        run_batch(reddit, args)


if __name__ == "__main__":
    main()
