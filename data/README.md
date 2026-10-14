# data/ — local, never committed

Everything under `data/` except this file is ignored by git because the
repository is public and the real files contain JAMA case text, answer keys,
model responses and grades. Back this folder up to your institution's
approved storage instead.

Put the source workbook at `data/source/` (any `.xlsx` name), then run
`python -m oe import` (see the top-level README).
