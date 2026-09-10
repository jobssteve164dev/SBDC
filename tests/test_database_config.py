from sbdc_api.config import Settings


def test_normalize_database_url_selects_installed_psycopg_driver() -> None:
    assert (
        Settings(
            database_url="postgresql://user:secret@database.example/sbdc"
        ).database_url
        == "postgresql+psycopg://user:secret@database.example/sbdc"
    )


def test_normalize_database_url_preserves_explicit_psycopg_driver() -> None:
    url = "postgresql+psycopg://user:secret@database.example/sbdc"

    assert Settings(database_url=url).database_url == url
