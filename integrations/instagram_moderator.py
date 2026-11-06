"""
Pulls comments from YOUR OWN Instagram Business/Creator account's posts
(via Meta's official Graph API) and runs each one through the Guardrail
Moderation API automatically. Optionally hides comments that get blocked.

Instagram does NOT allow free, open access to arbitrary public content the
way Reddit does — Meta only exposes comments on posts belonging to the
Instagram Professional (Business/Creator) account you control, and only
through their Graph API with a valid access token.

Setup (one-time, ~10-15 minutes):
  1. Convert your Instagram account to Professional (Business or Creator):
     Instagram app -> Settings -> Account type and tools -> Switch to
     professional account.
  2. Connect that Instagram account to a Facebook Page (Meta requires this;
     you'll be prompted during the step above, or do it in Meta Business
     Suite -> Settings -> Linked accounts).
  3. Create a Meta developer app at https://developers.facebook.com/apps
     -> "Create App" -> type "Business".
  4. In the app dashboard, add the "Instagram Graph API" product.
  5. Use the Graph API Explorer (https://developers.facebook.com/tools/explorer)
     to generate a User access token for your app with these permissions:
       instagram_basic, instagram_manage_comments,
       pages_show_list, pages_read_engagement
     (For quick testing, a short-lived token from the Explorer is fine --
     it's valid for about an hour. For anything longer-running, exchange it
     for a long-lived token per Meta's docs.)
  6. Find your Instagram Business Account ID: in the Graph API Explorer, call
       GET /me/accounts
     to find your connected Facebook Page ID, then call
       GET /{page-id}?fields=instagram_business_account
     to get your Instagram Business Account ID.
  7. Add all of this to your .env file:
       META_ACCESS_TOKEN=your_token
       IG_BUSINESS_ACCOUNT_ID=your_ig_business_account_id

Usage:
  # Check comments on your 5 most recent posts (one-time batch)
  python integrations/instagram_moderator.py --limit 5

  # Same, but also hide any comment that gets BLOCKED
  python integrations/instagram_moderator.py --limit 5 --auto-hide
"""
import argparse
import os
import sys

import requests

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def load_dotenv_if_present():
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


def get_credentials():
    token = os.environ.get("META_ACCESS_TOKEN")
    ig_account_id = os.environ.get("IG_BUSINESS_ACCOUNT_ID")
    if not token or not ig_account_id:
        print(
            "ERROR: META_ACCESS_TOKEN and IG_BUSINESS_ACCOUNT_ID must be set "
            "(in your .env file or as environment variables).\n"
            "See the setup steps in this script's docstring, or run with --help.",
            file=sys.stderr,
        )
        sys.exit(1)
    return token, ig_account_id


def get_recent_media(token: str, ig_account_id: str, limit: int) -> list:
    resp = requests.get(
        f"{GRAPH_API_BASE}/{ig_account_id}/media",
        params={"fields": "id,caption,permalink,timestamp", "limit": limit, "access_token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_comments(token: str, media_id: str) -> list:
    resp = requests.get(
        f"{GRAPH_API_BASE}/{media_id}/comments",
        params={"fields": "id,text,username,timestamp", "access_token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def hide_comment(token: str, comment_id: str):
    resp = requests.post(
        f"{GRAPH_API_BASE}/{comment_id}",
        params={"hide": "true", "access_token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def moderate_text(api_base: str, api_key: str, text: str) -> dict:
    """Calls this project's own POST /moderate/text endpoint."""
    resp = requests.post(
        f"{api_base}/moderate/text",
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        json={"text": text[:20000]},
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


def run(args):
    token, ig_account_id = get_credentials()

    print(f"Fetching your {args.limit} most recent Instagram posts...\n")
    media_items = get_recent_media(token, ig_account_id, args.limit)

    if not media_items:
        print("No posts found on this account.")
        return

    for media in media_items:
        caption = media.get("caption")
        if caption:
            try:
                result = moderate_text(args.api_base, args.api_key, caption)
                print_result(f"post {media['id']} caption", caption, result)
            except requests.RequestException as e:
                print(f"⚠️  Failed to moderate caption for post {media['id']}: {e}\n")

        try:
            comments = get_comments(token, media["id"])
        except requests.RequestException as e:
            print(f"⚠️  Failed to fetch comments for post {media['id']}: {e}\n")
            continue

        for comment in comments:
            text = comment.get("text", "")
            if not text:
                continue
            try:
                result = moderate_text(args.api_base, args.api_key, text)
                label = f"comment {comment['id']} (@{comment.get('username', 'unknown')})"
                print_result(label, text, result)

                if args.auto_hide and result["decision"] == "block":
                    hide_comment(token, comment["id"])
                    print(f"    -> hidden on Instagram\n")
            except requests.RequestException as e:
                print(f"⚠️  Failed to moderate comment {comment['id']}: {e}\n")


def main():
    load_dotenv_if_present()

    parser = argparse.ArgumentParser(description="Moderate your Instagram posts/comments with the Guardrail API")
    parser.add_argument("--limit", type=int, default=5, help="Number of most recent posts to check")
    parser.add_argument("--auto-hide", action="store_true", help="Automatically hide comments that get BLOCKED")
    parser.add_argument("--api-base", default=os.environ.get("MODERATION_API_BASE", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("API_KEY", "changeme-dev-key"))
    args = parser.parse_args()

    run(args)


if __name__ == "__main__":
    main()
