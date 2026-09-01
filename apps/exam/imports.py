"""
Reading a question bank out of an uploaded CSV.

Plain functions, deliberately. Nothing here takes a request or a form, so the
same code serves the import page and — when the Eklavya bank has to be moved
across — a management command. That migration is the reason this is a module
rather than a few helpers inside views.py: a command importing from views drags
in every decorator and every other view to use one parser.

The division of labour:

  read_csv(file)      the file as a whole — is it text, is it ours?  Raises.
  parse_row(cells, n) one row — collects what is wrong rather than raising,
                      so the preview page can report each row separately.

Only read_csv raises. A bad *file* is one message and there is nothing to show;
a bad *row* is one of five hundred, and refusing the whole upload over it means
an author fixes one typo at the cost of a full re-upload. They delete the
awkward row instead. So rows carry their errors and get skipped.
"""

import csv
import io
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Question

#: Ceiling on the upload. Django applies none of its own —
#: FILE_UPLOAD_MAX_MEMORY_SIZE only chooses memory over a temp file, and
#: DATA_UPLOAD_MAX_MEMORY_SIZE explicitly excludes file data — so this is the
#: only limit there is. Two megabytes is far more than MAX_ROWS of text, so
#: in practice the row cap is what an author actually meets.
MAX_SIZE = 2 * 1024 * 1024

#: Rows beyond this are refused rather than truncated. Silently importing the
#: first 500 of a 900-row file is the worst of the options.
MAX_ROWS = 500

#: The option columns, in order. A list, not a set: the position *is* the
#: option number, which is what correct_option refers to.
OPTION_COLUMNS = [f"option_{i}" for i in range(1, 7)]

#: Must be present, whatever kind of question the file holds. Deliberately
#: minimal — option columns are needed only by objective questions, so a file
#: of purely subjective ones legitimately has none, and demanding them here
#: would reject a valid file.
REQUIRED_COLUMNS = {"question_text"}

#: Everything the parser understands. REQUIRED is folded in, so a column is
#: unknown exactly when it is not in here.
KNOWN_COLUMNS = REQUIRED_COLUMNS | {
    "question_type",
    "question_difficulty",
    "marks",
    "question_tags",
    "correct_option",
    *OPTION_COLUMNS,
}


def read_csv(file):
    """
    Turns an uploaded file into a list of row dicts.

    Returns ``(rows, unknown_columns)``. Unknown columns are *returned*, not
    raised on: a team's working spreadsheet often carries its own bookkeeping
    columns, and refusing the file over an `author` column would be obnoxious.
    The caller shows them on the preview so a misspelled `question_tag` is
    noticed rather than silently dropped.

    Raises ValidationError for anything that makes the file unusable.

    There is no test here for "is this really a CSV", because there is no such
    test. CSV has no magic bytes and no header — any text file is a valid CSV
    of one column. What can be checked is whether it decodes as text and
    whether it has the columns we need, and the second of those has to happen
    anyway. The decode and NUL checks below earn their place purely on the
    error message: without them an author who uploads a spreadsheet gets
    `line contains NUL` instead of being told to save it as CSV.
    """
    if file.size > MAX_SIZE:
        raise ValidationError(
            f"That file is {file.size / 1024 / 1024:.1f} MB. "
            f"The limit is {MAX_SIZE // 1024 // 1024} MB."
        )

    # Read the bytes rather than wrapping the upload in a TextIOWrapper. The
    # wrapper closes the file underneath it when it is garbage collected, and
    # *when* that happens is unpredictable — so the upload can arrive at the
    # parser already closed, intermittently.
    file.seek(0)
    raw = file.read()

    # utf-8-sig strips Excel's byte-order mark if there is one and behaves
    # exactly like utf-8 if there is not, so it is always the right choice
    # here. Plain utf-8 leaves the BOM glued to the first header, which then
    # reads as "﻿question_text" and looks like a missing column on a file
    # that is perfectly fine.
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError(
            "That doesn't look like a CSV file. If it is a spreadsheet or a "
            "PDF, save it as CSV and try again."
        )

    # A .xlsx or .docx is a ZIP, and a ZIP sometimes decodes as UTF-8 without
    # complaint. NUL bytes are what gives it away. Left to itself the csv
    # module fails on this too, with a message no author can act on.
    if "\x00" in text:
        raise ValidationError(
            "That file is not plain text. If it is a spreadsheet, save it as "
            "CSV and try again."
        )

    reader = csv.DictReader(io.StringIO(text))

    # fieldnames is None for a completely empty file; without the `or []` that
    # is a TypeError rather than a readable message.
    header = set(reader.fieldnames or [])
    if not header:
        raise ValidationError("That file is empty.")

    missing = REQUIRED_COLUMNS - header
    if missing:
        # sorted(), so the message reads the same on every run — joining a set
        # directly gives a different order each time.
        raise ValidationError(
            f"Missing column(s): {', '.join(sorted(missing))}. "
            f"Download the template to see the expected header row."
        )

    # csv raises rather than returns on malformed input, and its errors are not
    # ValidationErrors — uncaught, they are a 500 rather than a message. The
    # common cause is an unclosed quote: everything after it becomes one field,
    # which then trips the module's 128 KB field cap.
    try:
        rows = list(reader)
    except csv.Error as exc:
        raise ValidationError(
            f"That file could not be read as CSV ({exc}). A likely cause is a "
            f'quotation mark that was opened and never closed.'
        )

    if len(rows) > MAX_ROWS:
        raise ValidationError(
            f"That file has {len(rows)} rows. The limit is {MAX_ROWS}. "
            f"Split it and import in batches."
        )

    return rows, sorted(header - KNOWN_COLUMNS)


@dataclass
class ParsedRow:
    """
    One CSV row, turned into the values a question needs plus a list of what is
    wrong with it.

    Field names match what templates/exam/import_questions.html renders, so the
    preview page can loop over these directly.

    `errors` empty means the row is expected to import. Expected, not
    guaranteed — see import_rows(): the forms are the authority, and this is a
    forecast made without touching the database.
    """

    number: int
    text: str = ""
    type: str = ""
    difficulty: str = ""
    marks: int | None = None
    tags: str = ""
    options: list[str] = field(default_factory=list)
    correct: int | None = None
    errors: list[str] = field(default_factory=list)


def _cell(cells, column):
    """
    One cell, as a clean string.

    csv.DictReader fills columns a short row omitted with None rather than "",
    so `cells.get(col, "")` is not enough on its own — the default only applies
    when the key is absent, and here it is present holding None.
    """
    return (cells.get(column) or "").strip()


def parse_row(cells, number):
    """
    Turns one CSV row into a ParsedRow, collecting problems rather than raising.

    `cells` is the raw dict from csv.DictReader — column name to cell value,
    every value a string. `row` is the object being built from it. Two names
    because they are two different things: what came out of the file, and what
    we made of it.

    Every check here is about the *shape* of the row — a type that is not one of
    the two, a correct_option pointing past the last option. Nothing here
    queries the database, so a 500-row preview costs no queries at all.

    These rules deliberately mirror QuestionForm.clean() and
    BaseAnswerOptionFormSet.clean(), which remain the authority. Duplicating
    them buys an accurate preview: without it a row would show as Ready and
    then be skipped at import, which is worse than the duplication. If you
    change a rule in forms.py, change it here too.
    """
    row = ParsedRow(number=number)
    row.text = _cell(cells, "question_text")
    row.tags = _cell(cells, "question_tags")

    if not row.text:
        row.errors.append("Question text is missing.")

    # --- type and difficulty -------------------------------------------------
    # Lowercased before matching, because a spreadsheet's autocapitalise turns
    # "objective" into "Objective" without anyone noticing.
    row.type = _cell(cells, "question_type").lower() or Question.Type.OBJECTIVE
    if row.type not in Question.Type.values:
        row.errors.append(
            f"question_type must be "
            f"{' or '.join(Question.Type.values)} — got “{row.type}”."
        )
        row.type = Question.Type.OBJECTIVE

    row.difficulty = _cell(cells, "question_difficulty").lower() or Question.Difficulty.EASY
    if row.difficulty not in Question.Difficulty.values:
        row.errors.append(
            f"question_difficulty must be "
            f"{', '.join(Question.Difficulty.values)} — got “{row.difficulty}”."
        )
        row.difficulty = Question.Difficulty.EASY

    # --- marks ---------------------------------------------------------------
    # Blank falls back to the model's own default rather than a number typed
    # here, so the two cannot drift. Objective rows are overwritten with
    # MARKS_PER_QUESTION by QuestionForm anyway; the column only means anything
    # for subjective questions.
    marks = _cell(cells, "marks")
    if not marks:
        row.marks = Question._meta.get_field("marks").default
    else:
        try:
            row.marks = int(marks)
        except ValueError:
            row.errors.append(f"marks must be a whole number — got “{marks}”.")
            row.marks = Question._meta.get_field("marks").default
        else:
            if row.marks < 1:
                row.errors.append("marks must be at least 1.")

    # --- options -------------------------------------------------------------
    # Blank columns are unused slots, not empty options, so they are dropped
    # rather than kept as "". That also means option_1,,option_3 collapses to
    # two options — and correct_option is checked against the collapsed list,
    # since that is what actually gets saved.
    row.options = [o for o in (_cell(cells, c) for c in OPTION_COLUMNS) if o]

    correct = _cell(cells, "correct_option")
    if correct:
        try:
            row.correct = int(correct)
        except ValueError:
            row.errors.append(
                f"correct_option must be a number between 1 and "
                f"{len(OPTION_COLUMNS)} — got “{correct}”."
            )

    if row.type == Question.Type.OBJECTIVE:
        if len(row.options) < 2:
            row.errors.append("An objective question needs at least two options.")
        if row.correct is None:
            if correct == "":
                row.errors.append("correct_option is missing.")
        elif not 1 <= row.correct <= len(row.options):
            row.errors.append(
                f"correct_option is {row.correct}, but this row has "
                f"{len(row.options)} option(s)."
            )
    else:
        if row.options:
            row.errors.append(
                "A subjective question is marked by an examiner, so it cannot "
                "carry options."
            )
        if correct:
            row.errors.append("correct_option does not apply to a subjective question.")

    return row


def _as_post_data(row, subject):
    """
    Shapes one ParsedRow into the dict the Add Question page would have posted.

    This is the whole trick behind import_rows: rather than a second definition
    of what a valid question is, the importer builds the same payload the form
    already knows how to validate and save. Tag normalising, the objective
    marks rule and the one-correct-answer rule all come along for free.
    """
    data = {
        "question_text": row.text,
        "question_subject": subject.pk,
        "question_type": row.type,
        "question_difficulty": row.difficulty,
        "marks": row.marks,
        "question_tags": row.tags,
        # A formset reads its size from the management form, not from how many
        # option keys it can find, so these four are not optional.
        "answers-TOTAL_FORMS": str(len(row.options)),
        "answers-INITIAL_FORMS": "0",
        "answers-MIN_NUM_FORMS": "0",
        "answers-MAX_NUM_FORMS": "1000",
    }
    for index, option in enumerate(row.options):
        data[f"answers-{index}-answer_option_text"] = option
        if index + 1 == row.correct:
            # "on" is what a ticked checkbox posts, and what CheckboxInput
            # reads back as True.
            data[f"answers-{index}-is_correct"] = "on"
    return data


def import_rows(rows, subject, user):
    """
    Writes the importable rows. Returns ``(created, failures)``, where failures
    is a list of ``(row_number, [messages])``.

    Rows that parse_row already rejected are skipped without being retried.
    Everything else goes through QuestionForm and AnswerOptionFormSet — the
    same pair the Add Question page uses — so there is one definition of a
    valid question rather than two that drift.

    A row can still fail here even though the preview showed it as Ready:
    parse_row never touches the database, so a rule that needs one (the subject
    still existing, say) only surfaces now. Those come back in `failures` for
    the caller to report.

    Imports are deliberately partial. One bad row in five hundred should not
    cost the other 499 — an author faced with re-uploading the whole file to
    fix one typo deletes the awkward row instead. Each question and its options
    are atomic together, so a row is never half-written.
    """
    # Imported here rather than at module scope: forms.py calls read_csv from
    # this module, so a top-level import of forms would be a cycle.
    from .forms import AnswerOptionFormSet, QuestionForm

    created, failures = 0, []

    for row in rows:
        if row.errors:
            continue

        data = _as_post_data(row, subject)
        form = QuestionForm(data, user=user)
        formset = AnswerOptionFormSet(
            data, instance=form.instance, form_kwargs={"user": user}
        )

        # Both asked, and in this order: form.is_valid() populates
        # form.instance, which the formset's clean() reads to learn the
        # question type. Two statements rather than `and`, so a row with
        # problems in both reports both.
        form_ok = form.is_valid()
        formset_ok = formset.is_valid()

        if not (form_ok and formset_ok):
            messages = [m for errors in form.errors.values() for m in errors]
            messages += list(formset.non_form_errors())
            failures.append((row.number, messages))
            continue

        with transaction.atomic():
            form.save()
            formset.save()
        created += 1

    return created, failures
