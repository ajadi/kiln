# Decisions

Append-only. Add rows with `python pipeline.py decide "<decision>" --options "<a / b>" --why
"<reason>" --by user|agent|proxy` (pipeline skill) or by hand in the same format. Superseded rows
stay; add a new row that names the old number.

| # | date | phase | decision | options | by | why |
|---|---|---|---|---|---|---|
