"""Atalho de compatibilidade: use `etl.pipelines.sync_ceap_emendas` (pipeline unificado e idempotente)."""

from etl.pipelines.sync_ceap_emendas import main as _main


def main():
    return _main(["--ano-inicio", "2003", "--ano-fim", "2026"])


if __name__ == "__main__":
    main()
