from pathlib import Path
from uuid import UUID

from services.ingestion.cli import build_arg_parser


def test_build_arg_parser_parses_required_arguments() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--tenant-id",
            "12345678-1234-5678-1234-567812345678",
            "--source",
            "local",
            "--path",
            "./sample_docs",
        ]
    )
    assert args.tenant_id == UUID("12345678-1234-5678-1234-567812345678")
    assert args.source == "local"
    assert args.path == Path("./sample_docs")


def test_build_arg_parser_rejects_unsupported_source() -> None:
    parser = build_arg_parser()
    try:
        parser.parse_args(
            [
                "--tenant-id",
                "12345678-1234-5678-1234-567812345678",
                "--source",
                "drive",
                "--path",
                "x",
            ]
        )
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("expected argparse to reject an unsupported --source value")
