"""Local NiceGUI presentation layer. All archive work runs in a background worker."""

import copy
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from nicegui import events, run, ui

from mailbucket import __version__
from mailbucket.branding import find_logo
from mailbucket.config import (
    DEFAULT_FOOTER_FIELDS,
    DEFAULT_PDF_FIELDS,
    FOOTER_LABELS,
    PDF_GROUPS,
    SEARCH_GROUPS,
    ExportOptions,
    PdfOptions,
    RunConfig,
    default_run_name,
)
from mailbucket.pipeline import ProgressUpdate, Result, execute
from mailbucket.search.matcher import parse_csv, parse_terms
from mailbucket.settings import Preferences, load_preferences, save_preferences


async def pick_path(*, directory: bool = False, start: Path | None = None) -> Path | None:
    """Local server-side picker avoids copying multi-gigabyte archives through the browser."""
    current = (start or Path.home()).expanduser().resolve()
    if not current.is_dir():
        current = current.parent
    with ui.dialog() as dialog, ui.card().classes("w-[760px] max-w-full"):
        ui.label("Ordner auswählen" if directory else "Datei oder Quellordner auswählen").classes(
            "text-xl"
        )
        path_input = ui.input("Pfad", value=str(current)).classes("w-full")
        listing = ui.column().classes("w-full h-80 overflow-auto gap-0")

        async def navigate(path: Path):
            nonlocal current
            try:
                path = path.expanduser().resolve()
                entries = await run.io_bound(
                    lambda: sorted(
                        path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())
                    )
                )
                current = path
                path_input.value = str(path)
                listing.clear()
                with listing:
                    ui.button(
                        ".. Übergeordneter Ordner", on_click=lambda: navigate(current.parent)
                    ).props("flat")
                    for item in entries:
                        if item.is_dir():
                            ui.button(
                                item.name + "/", icon="folder", on_click=lambda p=item: navigate(p)
                            ).props("flat")
                        elif not directory:
                            ui.button(
                                item.name,
                                icon="description",
                                on_click=lambda p=item: dialog.submit(p),
                            ).props("flat")
            except (OSError, ValueError) as error:
                ui.notify(str(error), type="negative")

        async def go():
            path = Path(path_input.value)
            if path.is_file() and not directory:
                dialog.submit(path.resolve())
            else:
                await navigate(path)

        path_input.on("keydown.enter", go)
        with ui.row():
            ui.button("Pfad öffnen", on_click=go).props("outline")
            ui.button("Diesen Ordner auswählen", on_click=lambda: dialog.submit(current))
            ui.button("Abbrechen", on_click=lambda: dialog.submit(None)).props("flat")
        await navigate(current)
    return await dialog


def open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def create_page() -> None:
    """Create isolated form state for each browser client."""
    ui.colors(primary="#0f766e", secondary="#334155", accent="#14b8a6")
    ui.add_css("""
        body { background: #f3f6f8; color: #172c3b; }
        .q-card { border: 1px solid #dce5e9; box-shadow: none; border-radius: 12px; }
        .section-title { font-weight: 600; font-size: 13px; letter-spacing: .08em; }
    """)
    sources: dict[Path, bool] = {}
    preferences = load_preferences()
    mappings = []
    mapping_text = ""
    last_result: Result | None = None
    busy = False
    progress_lock = threading.Lock()
    latest_progress: ProgressUpdate | None = None

    def report(update: ProgressUpdate):
        nonlocal latest_progress
        with progress_lock:
            latest_progress = update

    def poll():
        nonlocal latest_progress
        with progress_lock:
            state = latest_progress
            latest_progress = None
        if state:
            total = state.total
            progress_label.text = f"{state.phase} · " + (
                f"{state.done:,} / {total:,} ({state.done / total:.0%})"
                if total
                else "Gesamtanzahl noch unbekannt"
                if total is None
                else "Keine Elemente"
            )
            bar.props(remove="indeterminate") if total is not None else bar.props("indeterminate")
            bar.value = state.done / total if total else 0
            mailbox_label.text = f"Mailbox: {state.mailbox}"
            term_label.text = f"Suchbegriffe: {state.terms}"
            counters.text = (
                f"Geprüft: {state.analyzed:,} E-Mails · Treffer: {state.matched:,} E-Mails · "
                f"Exportiert: {state.exported:,} PDFs (inkl. Bucket-Kopien)"
            )
            hit_table.rows = [
                {"bucket": bucket, "hits": count} for bucket, count in state.hits.items()
            ]
            hit_table.update()

    def export_options() -> ExportOptions:
        return ExportOptions(
            timestamp_names=timestamp.value,
            include_attachments=include.value,
            pdf_mode=pdf_mode.value,
            images_as_pages=images.value,
            save_originals=originals.value,
            cover_pages=covers.value,
            pdf=PdfOptions(
                custom_header=pdf_header.value or "",
                fields=tuple(f for f, widget in pdf_widgets.items() if widget.value),
                footer_enabled=footer_enabled.value,
                footer_fields=tuple(f for f, widget in footer_widgets.items() if widget.value),
            ),
        )

    def save_settings(notify: bool = True):
        try:
            save_preferences(
                Preferences(
                    tuple(f for f, widget in field_widgets.items() if widget.value),
                    dedup.value,
                    export_options(),
                )
            )
            if notify:
                ui.notify(
                    "Such- und Exportoptionen für den nächsten Start gespeichert.", type="positive"
                )
        except OSError as error:
            ui.notify(f"Einstellungen konnten nicht gespeichert werden: {error}", type="warning")

    def set_selection(widgets: dict, selected: tuple[str, ...]):
        for key, widget in widgets.items():
            widget.value = key in selected

    def restore_pdf():
        set_selection(pdf_widgets, DEFAULT_PDF_FIELDS)

    def restore_footer():
        footer_enabled.value = True
        set_selection(footer_widgets, DEFAULT_FOOTER_FIELDS)

    @ui.refreshable
    def source_list():
        if not sources:
            ui.label("Noch keine Quellen. Archive bleiben auf diesem Computer.").classes(
                "text-slate-500"
            )
        for path in list(sources):
            with ui.row().classes("w-full items-center flex-nowrap"):
                ui.checkbox(
                    str(path),
                    value=sources[path],
                    on_change=lambda e, p=path: sources.__setitem__(p, e.value),
                ).classes("grow break-all")

                def remove(p=path):
                    sources.pop(p, None)
                    source_list.refresh()

                ui.button(icon="close", on_click=remove).props("flat round dense")

    async def add_source():
        path = await pick_path()
        if path:
            sources[path] = True
            source_list.refresh()

    async def load_terms(event: events.UploadEventArguments):
        nonlocal mappings, mapping_text
        try:
            text = (await event.file.read()).decode("utf-8-sig")
            if event.file.name.lower().endswith(".csv"):
                parsed = parse_csv(text)
                mapping_text = "\n".join(t.term for t in parsed)
                mappings = parsed
                terms_input.value = mapping_text
                mapping_note.text = f"CSV aktiv: {len(parsed)} Begriffe, {len({t.bucket for t in parsed})} Buckets. Änderungen im Textfeld setzen die Zuordnung zurück."
            else:
                terms_input.value = text
                mappings = []
                mapping_text = ""
                mapping_note.text = "TXT geladen. Ein Suchbegriff pro Zeile."
        except (UnicodeError, ValueError) as error:
            ui.notify(str(error), type="negative", timeout=8000)

    def terms_changed():
        nonlocal mappings
        if mappings and terms_input.value != mapping_text:
            mappings = []
            mapping_note.text = (
                "CSV-Zuordnung zurückgesetzt: Suchbegriffe sind jetzt auch Bucket-Namen."
            )

    async def choose_output():
        path = await pick_path(directory=True, start=Path(output_input.value))
        if path:
            output_input.value = str(path)

    async def start(dry: bool):
        nonlocal busy, last_result
        if busy:
            return
        try:
            config = RunConfig(
                sources=[p for p, selected in sources.items() if selected],
                terms=copy.deepcopy(mappings) if mappings else parse_terms(terms_input.value),
                output_dir=Path(output_input.value).expanduser().resolve(),
                run_name=run_input.value,
                search_fields=tuple(f for f, widget in field_widgets.items() if widget.value),
                deduplicate=dedup.value,
                export=export_options(),
            )
            config.validate()
            save_settings(notify=False)
            busy = True
            dry_button.disable()
            export_button.disable()
            folder_button.set_visibility(False)
            output_label.text = ""
            form.props("inert").style("opacity: .65")
            status.text = "Dry Run läuft …" if dry else "Export läuft …"
            last_result = await run.io_bound(execute, config, dry_run=dry, on_progress=report)
            poll()
            if last_result is None:
                raise RuntimeError("Verarbeitung wurde beim Herunterfahren unterbrochen.")
            stats = last_result.stats
            status.text = ("Dry Run abgeschlossen" if dry else "Export abgeschlossen") + (
                " – mit Fehlern, bitte Protokoll prüfen" if stats.errors else ""
            )
            summary.text = (
                f"{stats.analyzed:,} Nachrichten analysiert · {stats.exported:,} PDFs erzeugt · "
                f"{stats.duplicates:,} Duplikate erkannt ({stats.skipped_duplicates:,} übersprungen) · "
                f"{stats.attachment_errors:,} Anhangfehler · {stats.errors:,} Fehler · {stats.warnings:,} Warnungen"
            )
            hit_table.rows = [
                {"bucket": bucket, "hits": count} for bucket, count in stats.hits.items()
            ]
            hit_table.update()
            messages.value = "\n".join(last_result.messages) or "Keine Warnungen oder Fehler."
            folder_button.set_visibility(last_result.output is not None)
            if last_result.output:
                output_label.text = str(last_result.output)
                # Offer a fresh run name after success, while preserving custom name prefixes.
                number = 2
                base = config.run_name
                while (config.output_dir / f"{base}_{number}").exists():
                    number += 1
                run_input.value = f"{base}_{number}"
        except Exception as error:
            status.text = "Lauf konnte nicht abgeschlossen werden"
            ui.notify(str(error), type="negative", timeout=10000)
        finally:
            busy = False
            dry_button.enable()
            export_button.enable()
            form.props(remove="inert").style(remove="opacity: .65")
            bar.props(remove="indeterminate")

    with ui.column().classes("w-full max-w-6xl mx-auto p-4 md:p-8 gap-5"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.row().classes("items-center gap-5 flex-1 min-w-0"):
                logo = find_logo()
                if logo:
                    ui.image(logo).props('fit=contain alt="MailBucket"').classes(
                        "w-28 sm:w-36 shrink-0"
                    )
                else:
                    ui.label("MailBucket").classes("text-3xl font-semibold")
                ui.label(
                    "Durchsucht Mailboxes nach Suchbegriffen und legt Suchbegriffordner an."
                ).classes("text-slate-600 text-base flex-1 min-w-48")
            ui.badge("LOCAL ONLY", color="primary").props("outline")
        with ui.column().classes("w-full gap-5") as form:
            with ui.card().classes("w-full p-5"):
                ui.label("01  QUELLEN").classes("section-title")
                source_list()
                ui.button("Quelle hinzufügen", icon="add", on_click=add_source).props("outline")
                ui.label("MBOX · EML / EML-Ordner · Maildir · Takeout ZIP / TAR / TGZ").classes(
                    "text-xs text-slate-500"
                )
            with ui.row().classes("w-full items-stretch gap-5"):
                with ui.card().classes("flex-1 min-w-72 p-5"):
                    ui.label("02  SUCHBEGRIFFE").classes("section-title")
                    ui.label(
                        "Ein Suchbegriff pro Zeile – je Suchbegriff wird ein eigener Export-Ordner angelegt."
                    ).classes("text-slate-600")
                    terms_input = (
                        ui.textarea(
                            "Ein Suchbegriff pro Zeile",
                            placeholder="Müller GmbH\nProjekt Alpha\nRechnung 2025",
                        )
                        .classes("w-full")
                        .props("rows=7 outlined")
                    )
                    terms_input.on_value_change(terms_changed)
                    ui.upload(
                        label="TXT oder CSV laden (UTF-8)",
                        on_upload=load_terms,
                        auto_upload=True,
                        max_file_size=2_000_000,
                    ).props('accept=".txt,.csv"').classes("w-full")
                    mapping_note = ui.label(
                        "CSV: term,bucket – mehrere Begriffe können denselben Bucket verwenden."
                    ).classes("text-xs text-slate-500")
                with ui.card().classes("flex-1 min-w-72 p-5"):
                    ui.label("03  SUCHFELDER").classes("section-title")
                    field_widgets = {}
                    for group, fields in SEARCH_GROUPS.items():
                        with ui.expansion(group, value=group in {"Nachricht", "Personen"}).classes(
                            "w-full"
                        ):
                            for key, label in fields.items():
                                selected = key in preferences.search_fields or (
                                    "from" in preferences.search_fields
                                    and key in {"sender_name", "sender_email"}
                                )
                                field_widgets[key] = ui.checkbox(label, value=selected)
                    ui.label(
                        "Message-ID und Internet Message ID bezeichnen denselben Header. Anhangsuche: kein OCR, keine Office-Dateien."
                    ).classes("text-xs text-slate-500")
                    ui.separator()
                    dedup = ui.checkbox(
                        "Duplikate automatisch entfernen", value=preferences.deduplicate
                    )
            with ui.card().classes("w-full p-5"):
                ui.label("04  AUSGABE").classes("section-title")
                with ui.row().classes("w-full items-center"):
                    output_input = (
                        ui.input("Ausgabeordner", value=str(Path.home() / "MailBucket-Exports"))
                        .classes("grow")
                        .props("outlined")
                    )
                    ui.button("Auswählen", icon="folder_open", on_click=choose_output).props(
                        "outline"
                    )
                run_input = (
                    ui.input("Laufname", value=default_run_name())
                    .classes("w-full")
                    .props("outlined")
                )
                timestamp = ui.checkbox(
                    "Datum und Uhrzeit im Dateinamen", value=preferences.export.timestamp_names
                )
                ui.label(
                    "Chronologisch nummeriert, immer mindestens vier Stellen: 0001, 0002 …"
                ).classes("text-xs text-slate-500")
            with ui.card().classes("w-full p-5"):
                ui.label("05  ANHÄNGE").classes("section-title")
                include = ui.checkbox(
                    "Anhänge berücksichtigen", value=preferences.export.include_attachments
                )
                pdf_mode = ui.radio(
                    {
                        "merge": "PDFs an E-Mail-PDF anhängen",
                        "separate": "PDFs separat speichern",
                        "both": "Beides",
                    },
                    value=preferences.export.pdf_mode,
                )
                images = ui.checkbox(
                    "Bilder als PDF-Seiten einfügen", value=preferences.export.images_as_pages
                )
                originals = ui.checkbox(
                    "Originalanhänge zusätzlich speichern", value=preferences.export.save_originals
                )
                covers = ui.checkbox(
                    "Deckblatt vor integrierten Anhängen einfügen",
                    value=preferences.export.cover_pages,
                )
            with ui.card().classes("w-full p-5"):
                with ui.expansion("06  PDF-INHALT · Outlook-Memo-Stil", icon="article").classes(
                    "w-full"
                ):
                    ui.label(
                        "Kompakter Mailkopf, Nachrichtentext und separat auswählbare MailBucket-Metadaten."
                    )
                    pdf_header = (
                        ui.textarea(
                            "Freier Kopftext für jede exportierte Mail",
                            value=preferences.export.pdf.custom_header,
                        )
                        .props("outlined autogrow rows=2")
                        .classes("w-full")
                    )
                    ui.label("Der Text erscheint oben auf der ersten PDF-Seite.").classes(
                        "text-xs text-slate-500"
                    )
                    pdf_widgets = {}
                    with ui.row().classes("w-full gap-6 items-start"):
                        for group, fields in PDF_GROUPS.items():
                            with ui.column().classes("flex-1 min-w-60 gap-1"):
                                ui.label(group).classes("font-semibold")
                                for key, label in fields.items():
                                    pdf_widgets[key] = ui.checkbox(
                                        label, value=key in preferences.export.pdf.fields
                                    )
                    with ui.row():
                        ui.button(
                            "Alle auswählen",
                            on_click=lambda: set_selection(pdf_widgets, tuple(pdf_widgets)),
                        ).props("flat")
                        ui.button(
                            "Alle abwählen", on_click=lambda: set_selection(pdf_widgets, ())
                        ).props("flat")
                        ui.button("Standard wiederherstellen", on_click=restore_pdf).props(
                            "outline"
                        )
                    ui.label(
                        "Die Auswahl steuert den erzeugten Mailkopf und Metadatenbereich. Mailtext und Originalanhänge behalten ihren Inhalt."
                    ).classes("text-xs text-slate-500")
                with ui.expansion("07  PDF-FUSSZEILE", icon="format_align_center").classes(
                    "w-full"
                ):
                    footer_enabled = ui.checkbox(
                        "Fußzeile aktivieren", value=preferences.export.pdf.footer_enabled
                    )
                    footer_widgets = {}
                    with ui.row().classes("w-full gap-x-6"):
                        for key, label in FOOTER_LABELS.items():
                            footer_widgets[key] = ui.checkbox(
                                label, value=key in preferences.export.pdf.footer_fields
                            )
                            footer_widgets[key].bind_enabled_from(footer_enabled, "value")
                    with ui.row():
                        ui.button(
                            "Alle auswählen",
                            on_click=lambda: set_selection(footer_widgets, tuple(footer_widgets)),
                        ).props("flat")
                        ui.button(
                            "Alle abwählen", on_click=lambda: set_selection(footer_widgets, ())
                        ).props("flat")
                        ui.button("Standard wiederherstellen", on_click=restore_footer).props(
                            "outline"
                        )
                    ui.label(
                        "Seitenzahlen zählen alle Anhänge mit. Für die Fußzeile wird unter jeder Seite zusätzlicher Platz angelegt."
                    ).classes("text-xs text-slate-500")
                ui.button(
                    "Einstellungen speichern", icon="save", on_click=lambda: save_settings()
                ).props("outline")
                ui.label(
                    "Optionen werden auch beim Start eines Laufs gespeichert. Quellen und Suchbegriffe werden nicht dauerhaft gespeichert."
                ).classes("text-xs text-slate-500")
        with ui.row().classes("gap-3"):
            dry_button = ui.button("Dry Run", icon="search", on_click=lambda: start(True)).props(
                "outline size=lg"
            )
            export_button = ui.button(
                "Export starten", icon="picture_as_pdf", on_click=lambda: start(False)
            ).props("size=lg")
        with ui.card().classes("w-full p-5"):
            status = ui.label("Bereit").classes("text-lg font-semibold")
            progress_label = ui.label("Der Dry Run prüft Treffer, ohne PDFs zu schreiben.").classes(
                "text-slate-500"
            )
            bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
            mailbox_label = ui.label("").classes("break-all")
            term_label = ui.label("").classes("break-all")
            counters = ui.label("")
            summary = ui.label("")
            hit_table = ui.table(
                columns=[
                    {"name": "bucket", "label": "Bucket", "field": "bucket", "align": "left"},
                    {"name": "hits", "label": "Treffer", "field": "hits"},
                ],
                rows=[],
                row_key="bucket",
            ).classes("w-full")
            with ui.expansion("Warnungen und Fehler (max. 100 Einträge)").classes("w-full"):
                messages = ui.textarea().props("readonly rows=6").classes("w-full")
            output_label = ui.label("").classes("break-all")
            folder_button = ui.button(
                "Ausgabeordner öffnen",
                icon="folder_open",
                on_click=lambda: (
                    open_folder(last_result.output) if last_result and last_result.output else None
                ),
            )
            folder_button.set_visibility(False)
        ui.label(
            f"MailBucket {__version__} · MIT · Vollständig lokale Verarbeitung · {datetime.now().year}"
        ).classes("text-xs text-slate-500")
    ui.timer(0.2, poll)


def launch(host: str = "127.0.0.1", port: int = 8080, show: bool = True) -> None:
    ui.run(
        root=create_page,
        host=host,
        port=port,
        title="MailBucket",
        reload=False,
        show=show,
        language="de",
        favicon="📬",
        show_welcome_message=False,
    )
