# Rheum Omics Monitor

Biweekly monitor for public rheumatology single-cell and spatial transcriptomics datasets. It queries public metadata sources, groups results by disease, and emails a concise report through SMTP.

## What it does

- Searches NCBI GEO, NCBI SRA, ENA, and CELLxGENE Discover.
- Filters for rheumatology diseases plus single-cell, single-nucleus, or spatial transcriptomics terms.
- Groups results by disease such as RA, SLE / lupus nephritis, myositis, and psoriasis / PsA.
- Sends a twice-monthly email report using SMTP credentials stored as GitHub Actions Secrets.

## Cloud schedule

The workflow in `.github/workflows/rheum-omics-monthly.yml` runs on the 1st and 15th day of each month at 01:00 UTC, which is 09:00 Beijing time.

Manual setup instructions are in `GITHUB_DEPLOYMENT.md`.

## Local use

See `rheum_omics_monitor/README.md` for local `.env` setup and test commands.
