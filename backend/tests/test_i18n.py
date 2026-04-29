import json
from pathlib import Path

I18N_DIR = Path(__file__).resolve().parents[1] / "app" / "static" / "i18n"
LOCALES = ("en", "de", "zh")
REQUIRED_KEYS = {
    "nav.demo",
    "nav.history",
    "upload.button.choose",
    "upload.button.batch",
    "form.field.model",
    "form.field.vinOrBin",
    "form.field.serialNumber",
    "form.category.title",
    "form.category.a",
    "form.category.b",
    "form.category.c",
    "ocr.processing",
    "ocr.confidence",
    "barcode.title",
    "barcode.fillSku",
    "duplicate.title",
    "duplicate.action.overwrite",
    "duplicate.action.discardNew",
    "history.column.id",
    "history.column.category",
    "history.column.model",
    "history.column.vin",
    "history.column.sn",
    "history.column.status",
    "history.column.createdAt",
    "history.column.actions",
    "history.filter.status",
    "history.filter.keyword",
    "history.filter.dateFrom",
    "history.filter.dateTo",
    "history.button.export",
    "history.button.refresh",
    "history.button.viewImage",
    "history.button.copySn",
    "history.button.viewRawOcr",
    "history.button.page",
    "status.uploaded",
    "status.ocrDone",
    "status.confirmed",
    "status.submitted",
    "status.submissionFailed",
    "status.duplicate",
    "status.needsReview",
    "error.upload415",
    "error.uploadGeneric",
    "error.ocrTimeout",
    "error.networkError",
    "error.missingFields",
    "guide.title",
    "guide.item1",
    "guide.item2",
    "guide.item3",
    "guide.item4",
    "guide.item5",
    "common.save",
    "common.cancel",
    "common.confirm",
    "common.retry",
    "common.skip",
    "common.loading",
    "common.yes",
    "common.no",
    "common.all",
}


def load_locale(locale: str) -> dict[str, str]:
    path = I18N_DIR / f"{locale}.json"
    assert path.exists(), f"missing locale file: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_i18n_locale_files_have_identical_non_empty_keys() -> None:
    catalogs = {locale: load_locale(locale) for locale in LOCALES}
    key_sets = {locale: set(messages) for locale, messages in catalogs.items()}

    assert key_sets["en"] == key_sets["de"] == key_sets["zh"]
    assert REQUIRED_KEYS <= key_sets["zh"]

    for locale, messages in catalogs.items():
        for key, value in messages.items():
            assert isinstance(value, str), f"{locale}:{key} is not a string"
            assert value.strip(), f"{locale}:{key} is empty"
