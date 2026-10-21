"""Compatibility entry point for the offline local-upload UI.

Escapes the embedded JavaScript newline in older local_upload.py revisions.
This is an offline loopback-only service; no poker site connectivity.
"""
import local_upload


def main():
    local_upload.HTML = local_upload.HTML.replace("status.append('\n')", "status.append('\\n')")
    local_upload.main()


if __name__ == '__main__':
    main()
