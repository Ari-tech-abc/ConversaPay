"""Preview a real product announcement; --publish queues mail to opt-in users."""
import argparse
from pathlib import Path
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-id', type=UUID, required=True, help='Stable UUID for this release; reuse it to avoid duplicate announcements')
    parser.add_argument('--title', required=True)
    parser.add_argument('--body-file', type=Path, required=True, help='UTF-8 plain-text announcement')
    parser.add_argument('--publish', action='store_true', help='Persist and queue this announcement for subscribed users')
    args = parser.parse_args()
    title, body = args.title.strip(), args.body_file.read_text(encoding='utf-8').strip()
    if not title or not body or len(title) > 200 or len(body) > 10000:
        parser.error('Provide a title up to 200 characters and body up to 10000 characters')
    if not args.publish:
        print(f'Preview only; no email queued.\nRelease: {args.release_id}\n{title}\n\n{body}')
        return
    from backend.config import settings
    from supabase import create_client
    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    existing = db.table('product_announcements').select('id,title,body').eq('id', str(args.release_id)).limit(1).execute().data
    if existing:
        if existing[0]['title'] != title or existing[0]['body'] != body:
            raise SystemExit('Release ID already exists with different content')
        print('This release was already published; no duplicate mail queued.')
        return
    db.table('product_announcements').insert({'id': str(args.release_id), 'title': title, 'body': body}).execute()
    print(f'Published release {args.release_id}; mail queued only for users who opted in.')


if __name__ == '__main__':
    main()
