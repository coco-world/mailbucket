import argparse
import logging


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MailBucket – lokale Mailarchiv-Suche und PDF-Export"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        choices=["127.0.0.1", "localhost", "::1"],
        help="Loopback-Adresse (nur lokale Verbindungen)",
    )
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--no-browser", action="store_true", help="Browser nicht automatisch öffnen"
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port muss zwischen 1 und 65535 liegen.")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    from mailbucket.app import launch

    try:
        launch(args.host, args.port, not args.no_browser)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("MailBucket beendet.")


if __name__ == "__main__":
    main()
