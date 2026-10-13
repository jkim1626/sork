# Sork Lab ecological data portal

A Python/Plotly Dash portal for exploring, joining, visualizing, downloading, and contributing ecological research data stored in Microsoft SQL Server. The implementation supports the Sork Lab's oak research and provides a starting point for other long-term collaborative studies.

**Version reference:** the application code described here was reviewed at commit [`e43cdae`](https://github.com/jkim1626/sork/tree/e43cdae968ddfca5201feb52e2fd42248803498c). The setup instructions use `main`. This guide documents the reviewed implementation, not an independently verified live deployment.

The repository supplies the portal application. An adopting team must supply the database, data model, metadata, credentials, authentication configuration, hosting, and maintenance arrangements. It is a case-study implementation that requires adaptation, rather than a complete installation of the research database.

## Contents

- [System overview](#system-overview)
- [Repository guide and execution order](#repository-guide-and-execution-order)
- [Infrastructure and responsibilities](#infrastructure-and-responsibilities)
- [Technical setup guide](#technical-setup-guide)
- [Adapting the portal to another study](#adapting-the-portal-to-another-study)
- [Troubleshooting](#troubleshooting)
- [Companion data-preparation workflow](#companion-data-preparation-workflow)

## System overview

```text
Raw observations + metadata
    -> study-specific standardization and QA/QC
    -> approved SQL Server source tables
    -> portal: explore, filter, join, analyze, map, export
    -> curated release with metadata in an archival repository

Contributed Excel workbook
    -> template/header validation and preview
    -> SQL Server holding table
    -> steward review and promotion to source tables outside this portal
```

The current interface has three main tabs:

| Tab | Features | Availability in the layout |
| --- | --- | --- |
| **Select and Filter** | Core-table selection; optional maternal-tree join; year/site filters; data grid; calculated columns; regression, PCA, summary statistics, and plots, including supported “color by” options; CSV exports | Guests and signed-in users |
| **Tree Sites** | Site and individual-tree maps, location/year/data filters, a dataset-availability grid linked to map filtering, identifier search, coordinate/detail exports, and a temporary CSV/TSV map overlay | Guests and signed-in users |
| **Flat File Downloads/Uploads** | **Download/Browse:** table preview and full-table CSV export. **Upload:** Excel template download, validation, preview, and submission to a holding table | Signed-in users |

There are two distinct upload workflows. The **Upload** subtab stages `.xlsx` records in SQL Server. A **Tree Sites** CSV/TSV upload creates a map overlay held in browser session storage; it does not insert records into source or holding tables.

### Access model and current boundaries

[app.py](app.py) selects guest or authenticated layouts using Auth0 session information. In [tabs/joins.py](tabs/joins.py), `_fetch_for_user()` routes guest queries through the public database credentials and signed-in queries through the standard read credentials. Holding-table writes use separate upload credentials.

These are shared credential tiers, not a complete per-user/per-dataset authorization system. Two implementation details matter when configuring public access:

- If public credentials are incomplete or treated as placeholders, `get_engine("public")` falls back to the standard read credentials and logs a warning.
- The map uses the standard read wrapper even in the guest layout. Its database access is not routed through `_fetch_for_user()`.

Configure and test server-side access controls before using restricted data. Layout visibility alone does not protect callback endpoints, downloads, or writes. Guest layouts also include the exports provided by Select and Filter and Tree Sites.

The repository does not supply database creation/migration scripts, a complete example database, the source datasets, a full data dictionary, a holding-table approval/promotion interface, automated backups, or automatic archival deposit/EML generation.

## Repository guide and execution order

| Path | Purpose | What to adapt |
| --- | --- | --- |
| [app.py](app.py) | Flask/Dash entry point, Auth0 routes, guest/authenticated tab sets, and flat-file subtabs | Branding, URLs, access policy, enabled tabs |
| [components/shell.py](components/shell.py) | Shared page shell, headers, footers, and main-tab construction | Layout and branding; `clone_tab()` supplies missing main-tab values from IDs |
| [data_access/sql.py](data_access/sql.py) | Database connections, table validation, schema access, upload-template metadata, row retrieval, and holding-table writes | Credential tiers, allowed tables, template mappings, schema and staging policy |
| [data_access/__init__.py](data_access/__init__.py) | Exports data-access helpers | Keep aligned with helper changes |
| [database.py](database.py) | Compatibility wrappers for standard and public read queries | Existing callers and error handling |
| [tabs/joins.py](tabs/joins.py) | Select and Filter, optional joins, calculations, analysis, figures, and CSV exports | Core tables, keys, scientific assumptions, filtering and access behavior |
| [tabs/map.py](tabs/map.py) | Maps, availability grid, filters, searches, overlays, and exports | Map sources, identifiers, geography, common-garden references, visibility |
| [tabs/download.py](tabs/download.py) | Full-table browser/download workflow | Download table list and access policy |
| [tabs/upload.py](tabs/upload.py) | Excel templates, schema display, exact-header validation, preview, and staged submission | Template choices and validation rules |
| [requirements.txt](requirements.txt) | Python dependencies, including `openpyxl==3.1.5` for Excel | Test and record dependency changes; most versions are pinned, while `click` uses a lower bound |
| [assets/custom.css](assets/custom.css) | Application styling | Branding and accessibility |
| [california_counties.geojson](california_counties.geojson) | Included geographic asset | Current map code does not read this file; replacing it alone does not alter the map |
| [.gitignore](.gitignore) | Excludes `.env`, the local virtual environment, and other local files | Keep secrets and private research data out of commits |

The root-level `refactor_joins.py`, `refactor_plot_data.py`, `split_layout.py`, `add_resizable_divider.py`, `add_resizable_divider_v2.py`, and `undo_resizable_divider.py` are source-editing utilities. They are not data-preparation steps or installation commands. Do not run them as part of setup.

**Execution order:** configure services and environment first, then run `python app.py`. Imports register the layouts and callbacks; browser interactions invoke database operations. Do not execute tab modules individually. The current implementation does not contain the former `tabs/dataset.py` or `tabs/stats.py`; their corresponding workflows are now represented within Select and Filter and the flat-file browser.

## Infrastructure and responsibilities

The architecture does not require UCLA-hosted services. An institution or contracted provider can supply equivalent services, but the database engine, authentication integration, study names, map references, and URLs must match the chosen deployment.

| Requirement | Local evaluation | Shared deployment | Responsible role |
| --- | --- | --- | --- |
| Application runtime | Computer with Git and Python | Maintained host/VM with a production Python web service | Application maintainer / IT |
| Database | Reachable test SQL Server with non-sensitive records | SQL Server with source, metadata, and holding tables; appropriate read/public/upload permissions | Database administrator |
| Database driver | Microsoft ODBC Driver 17 and OS prerequisites | Driver installed on the application host | IT |
| Identity | Auth0 application and test account | Auth0 tenant/application and account lifecycle management | Identity administrator |
| Network | Database and Auth0 connectivity | DNS, HTTPS, firewall rules, and approved database connectivity | IT |
| Storage | Test database and project files | Source data, metadata, holding batches, indexes, transaction logs, backups, and export working space | IT + data steward |
| Continuity | Repeatable setup notes | Primary and backup maintainers, recovery runbook, and handover process | Project lead |

No measured CPU/RAM/storage minimum, maximum dataset size, concurrent-user benchmark, or deployment-time estimate is supplied. Test with representative data and concurrent users. Several features can load full result sets into memory, and browser grids also consume client memory.

Before requesting hosting, record current data volume and annual growth, largest export/workbook, concurrent users, sensitivity, backup retention, acceptable recovery time, and funding responsibility. Include database licensing, identity services, hosting, and maintenance in the local cost assessment. Existing institutional services may reduce setup work, but do not remove the need for named owners.

## Technical setup guide

“User-specific” below identifies services, decisions, or artifacts supplied by the adopting team.

| Step | Action | Code reference | User-specific work |
| --- | --- | --- | --- |
| 1 | Define the data model and responsibilities | Outside the portal | Identifiers, dictionary, QA/QC, roles |
| 2 | Obtain the code and dependencies | `requirements.txt` | Python and OS software |
| 3 | Prepare database, templates, and driver | `data_access/sql.py` | Tables, metadata, accounts, permissions |
| 4 | Register authentication | `app.py` | Auth0 application and URLs |
| 5 | Configure the environment | Local `.env` | Connection details and table settings |
| 6 | Adapt the study-specific interface | `tabs/joins.py`, `tabs/map.py`, `components/shell.py` | Keys, labels, geography, workflow choices |
| 7 | Start and verify locally | `app.py` | Test records and functional checks |
| 8 | Deploy and maintain | Application and host configuration | Authorization, hosting, recovery, stewardship |

### Step 1: Define the data model and responsibilities

Define the observation unit and persistent identifiers, including the keys that distinguish repeated observations across dates, sites, and individuals. Specify relationships and uniqueness rules before loading data.

Create a data dictionary covering column names, descriptions, types, units, missing-value codes, allowed values, and keys. Preserve raw files and record cleaning decisions, methods, contributors, coordinate reference systems, and versions. Define checks for duplicate records, invalid dates, inconsistent units, implausible values, and missing relationships.

Assign responsibility for reading, contributing, approving, correcting, publishing, and administering data. Template/header checks are only one part of scientific QA/QC.

**Completion check:** a data model, dictionary, QA/QC plan, and ownership/access plan exist.

### Step 2: Obtain the code and dependencies

The inherited repository README identifies Python **3.11.11**. Use Python 3.11 as the documented starting point; record the exact interpreter and installed package versions used in your deployment.

```bash
git clone --branch main --single-branch https://github.com/jkim1626/sork.git
cd sork
```

macOS/Linux:

```bash
python3.11 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Use your institution's supported environment procedure if activation or software installation is managed centrally. Run subsequent commands from the repository root with the environment active.

```bash
python --version
python -m pip check
```

**Completion check:** dependencies install successfully. `openpyxl` is already included in requirements.txt. Python dependency installation does not install SQL Server or Microsoft's system ODBC driver.

### Step 3: Prepare SQL Server, templates, and the driver

Obtain a test database and database accounts. Queries use SQL Server syntax and the `dbo` schema; replacing SQL Server with PostgreSQL or SQLite requires code changes.

Prepare separate standard-read, public-read, and upload account configurations. Public access should be restricted at the database and application layers. Source/template metadata are read with the standard-read connection; staged rows are written to the upload connection's database, which may be a separate database.

Create and populate approved source tables through database tools. For the default Excel upload choices, provide these metadata tables:

| Upload choice | Metadata table in `dbo` |
| --- | --- |
| `common_garden_yearly_census` | `qplad_template_census_meta` |
| `common_garden_generic` | `qplad_template_commongarden_generic_meta` |
| `adult_tree_generic` | `qplad_template_adult_generic_meta` |

Each mapped metadata table must contain rows with **`Variable`, `Type`, `Required`, and `Description`** columns. The code constructs template headers from `Variable` and displays the other fields as guidance. Mapped metadata that is missing, inaccessible, or empty causes an error; it does not silently fall back to a source table.

For another study, set `UPLOAD_TEMPLATE_TABLES` and either update `UPLOAD_TEMPLATE_TARGETS` in [data_access/sql.py](data_access/sql.py), or use names without a mapping and provide corresponding physical tables whose schemas can be read. The default choices are logical template names; they need not themselves be source tables when metadata mappings exist.

Template metadata is currently queried without an `ORDER BY`, even though upload validation requires exact column order. Before shared use, establish a deterministic ordering field/query so template generation and later validation use the same order.

Submissions are appended to `dbo.upload_holding_<normalized_template_name>` in the upload database. The name is lowercased and non-alphanumeric separators are replaced with underscores. Each batch adds:

- `upload_batch_id`
- `source_table` (the selected template name)
- `source_filename`
- `uploaded_at_utc`

Pre-create holding tables with appropriate types and grant the required insert permissions, or explicitly arrange permission for pandas `to_sql()` to create them when absent. Avoid template-column collisions with the four traceability columns. Define an external review/promotion procedure; the portal does not automatically approve or merge staged rows into source data. Repeated submissions can create duplicate batches.

Install [Microsoft ODBC Driver 17 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) and verify it:

```bash
python -c "import pyodbc; print(pyodbc.drivers())"
```

The driver name is centralized in `_build_connection_string()` in `data_access/sql.py`. If your host requires a different driver, update that function and test its connection settings.

**Completion check:** intended accounts can reach the required databases, read permitted source/metadata tables, and insert into designated holding tables.

### Step 4: Register authentication

Create an Auth0 **Regular Web Application**, configure a connection/test account, and record its domain, client ID, and client secret. See [Auth0's setup guidance](https://auth0.com/docs/get-started/authentication-and-authorization-flow/authorization-code-flow/add-login-auth-code-flow).

For local development configure:

- Allowed Callback URL: `http://127.0.0.1:8050/callback`
- Allowed Logout URL: `http://127.0.0.1:8050`

Use `127.0.0.1` consistently. For deployment, update the hard-coded return URLs in both `/logout` and `/unauthorized` in [app.py](app.py), and configure the corresponding HTTPS URLs in Auth0. Setting `AUTH0_CALLBACK_URL` alone does not change the logout destinations. Test normal logout and the error return path.

**Completion check:** Auth0 URLs match the application and a test account exists.

### Step 5: Configure the environment

Create `.env` in the repository root. Replace these illustrative values with actual test configuration; table names must exist or be adapted as described above.

```dotenv
# Standard reads and metadata access
DB_SERVER=your-sql-host
DB_DATABASE=your-source-database
DB_USERNAME=your-read-login
DB_PASSWORD=your-read-password

# Public queries in Select and Filter
DB_PUBLIC_SERVER=your-sql-host
DB_PUBLIC_DATABASE=your-public-database
DB_PUBLIC_USERNAME=your-public-login
DB_PUBLIC_PASSWORD=your-public-password

# Holding-table writes
DB_UPLOAD_SERVER=your-sql-host
DB_UPLOAD_DATABASE=your-staging-database
DB_UPLOAD_USERNAME=your-upload-login
DB_UPLOAD_PASSWORD=your-upload-password

AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
AUTH0_CALLBACK_URL=http://127.0.0.1:8050/callback
APP_SECRET_KEY=replace-with-a-generated-random-secret

TABLE_OPTIONS=db_main,budburst_detailed_all,biomass_destructive_2021,leaf_traits_2016
MAP_TABLE=dat_avail_db
DAT_AVAIL_TABLE=dat_avail_db
UPLOAD_TEMPLATE_TABLES=common_garden_yearly_census,common_garden_generic,adult_tree_generic
```

Generate a secret locally and place it in `APP_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

| Setting | Meaning |
| --- | --- |
| `DB_*` | Standard database reads, including map queries and template metadata |
| `DB_PUBLIC_*` | Public-query connection used by Select and Filter; configure all four values and verify permissions. Missing/placeholder settings trigger fallback to standard reads |
| `DB_UPLOAD_*` | Connection for holding-table writes; required to submit workbooks |
| `AUTH0_DOMAIN` | Tenant hostname without `https://` or a trailing slash |
| `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_CALLBACK_URL` | Registered application credentials and exact callback URL |
| `APP_SECRET_KEY` | Random Flask session-signing secret; replace the code's fallback |
| `TABLE_OPTIONS` | Comma-separated, unqualified names for the flat-file browser; whitespace is trimmed and empty entries ignored |
| `UPLOAD_TEMPLATE_TABLES` | Separate upload-choice list; omitted/empty values use the three defaults in `data_access/sql.py` |
| `MAP_TABLE` | Primary mappable SQL table |
| `DAT_AVAIL_TABLE` | Optional availability-grid table; when omitted, the grid uses `MAP_TABLE` |

`TABLE_OPTIONS` does not configure the core-table menu in Select and Filter, the map, or the upload templates. Those have separate settings/constants. Use unqualified names without `dbo.`; the shared identifier validator permits names beginning with a letter/underscore and containing letters, digits, underscores, or spaces.

`load_dotenv(override=True)` lets `.env` override host-provided environment variables. Keep deployment configuration consistent and never commit secrets. Connection credentials are interpolated into a SQLAlchemy URL; if they contain reserved URL characters, update connection construction to handle them correctly rather than weakening passwords.

**Completion check:** all settings needed by enabled features are supplied; `.env` remains excluded from Git.

### Step 6: Adapt study-specific features

**Select and Filter:** edit `CORE_TABLES`, `MATERNAL_TREE_TABLE`, `CORE_JOIN_KEYS_BY_TABLE`, `DEFAULT_CORE_JOIN_KEYS`, `TREE_JOIN_KEYS`, and corresponding SQL/callbacks in [tabs/joins.py](tabs/joins.py).

The core menu currently contains `db_main`, `budburst_detailed_all`, `biomass_destructive_2021`, and `leaf_traits_2016`. Default keys are `Accession`, `Locality`, `Year`, and `Site`; leaf traits omit `Year`. When maternal variables are selected, the code joins `Valley oak maternal tree climate data BCM 2018_03_08` on `Accession` and `Locality`. Core data can also be viewed without selecting maternal variables. The current implementation does not contain the older separate garden-climate join.

Check join cardinality and unmatched records. Duplicate maternal keys can multiply records; `SELECT DISTINCT` does not prove scientific correctness. Review casts and filter assumptions when replacing the oak identifiers.

**Tree Sites:** the primary map expects numeric `Latitude` and `Longitude` and a locality-name column resolved as `locality_full_name`/`Locality_full_name`. `Accession`, `sample_id`, `Year`, and `Site` support optional features. Verify that the selected identifier column exists before relying on search results.

The availability grid reads up to 500 rows from `DAT_AVAIL_TABLE` or the primary map table. Its supported filters are translated to map queries for columns that also exist in the map table; a separate availability table does not create a relational join automatically. Test correspondence between the grid filters and mapped records.

Adapt the hard-coded `dat_cgp_db` common-garden layer, California extent, UCLA marker, Chico/Placerville reference sites, and `IFG` alias. Reference coordinates have a TODO in the source and should be checked against your approved site coordinates. Special handling of `dat_avail_db` can query `db_main` for years via `Locality`; replace that logic for another data model. CSV/TSV overlays retain at most 10,000 usable coordinate rows and discard rows with unusable numeric coordinates. Identifier search also caps results at 10,000 rows.

**Branding and enabled features:** update [components/shell.py](components/shell.py), [app.py](app.py), and [assets/custom.css](assets/custom.css). To omit maps or Select and Filter, remove the relevant imports and entries from both `TAB_SPECS` and `GUEST_TAB_SPECS`, and update the default active tab in both layout builders. Keep the resulting guest layout valid. Main-tab values are supplied by the shell helper; separately verify flat-file subtab values and activation callbacks if changing those components.

**Completion check:** every enabled feature matches your tables, identifiers, geography, and intended access policy.

### Step 7: Start and verify locally

Test a standard read, then start the development application:

```bash
python -c "from database import fetch_data_from_sql; print(fetch_data_from_sql('SELECT 1 AS connection_ok', raise_on_error=True))"
python app.py
```

Open `http://127.0.0.1:8050/`. This runs Dash with debug enabled and the reloader disabled; it is a local development command.

Use non-sensitive test data and record the results:

1. Verify guest and authenticated layouts, login/logout, and failed-login behavior. Confirm which database account each public feature actually uses.
2. In **Select and Filter**, select a core table, choose variables/filters, and compare returned values and optional joins against known records. Test calculated columns and figures, including supported color grouping.
3. Check analysis scope. Regression/PCA/summary helpers prefer the loaded grid with its filters; their query fallback uses at most 50,000 rows. Plot Data and filtered export can prioritize selected rows. Row limits are not random sampling, and the workflows do not all use selections identically.
4. Compare exports. Select and Filter's filtered export uses selected rows, otherwise filtered grid rows, otherwise loaded rows. Its “all” export re-runs the base query, retaining base year/site filters but excluding later grid filters and locally calculated columns. Flat-file downloads export **all rows and columns**, regardless of preview row limits or grid filters.
5. Check map locations, availability filters, identifier searches, temporary overlays, and coordinate/detail exports. Confirm sensitive locations are not exposed through guest features.
6. Download an Excel upload template, fill its `Data` sheet, and submit a small test workbook. The template also includes `Schema` and `README` sheets. The parser uses `Data` when present, otherwise the first sheet, and drops completely empty rows.
7. Verify exact header names/order and nonempty-data checks, then confirm the submitted rows and traceability fields appear in the upload database's holding table. Source tables should remain unchanged. Check rejection of a changed header and the treatment of missing cells. Displayed type/required-field guidance is not comprehensive enforcement of data types, conditional requirements, duplicates, units, or ecological validity.

**Completion check:** document the code commit, interpreter/packages, expected and actual results, and any unresolved behavior. A functioning login alone does not validate the workflow.

### Step 8: Deploy and maintain

The host must configure a production WSGI service for `app:server`, HTTPS, process supervision, environment, logging, and monitoring. A production server package/service configuration is not supplied here. Update the Auth0 return URLs and replace the fallback application secret.

Complete server-side authorization for protected callbacks, exports, and submissions. Review client-supplied selections and stored query text, validate permitted identifiers server-side, and use parameterized values. Configure least-privilege accounts, explicitly address the public fallback and map routing, and test denied access as well as allowed access.

The connection string encrypts traffic but uses `TrustServerCertificate=yes`. Have the host configure a trusted SQL Server certificate and verified TLS in `data_access/sql.py` before relying on certificate validation.

| Continuing task | Suggested owner | When |
| --- | --- | --- |
| Review holding batches, QA/QC, duplicates, and promotion to source data | Data steward | Each submission |
| Update metadata and version schema/template changes | Data steward + developer | Each schema change |
| Add/remove collaborator access | Project lead / identity administrator | Onboarding, departure, periodic review |
| Back up source and staging databases, metadata, raw files, and configuration | Database/host administrator | Agreed retention/recovery schedule |
| Test restoration in a separate environment | Database/host administrator | Agreed schedule and major infrastructure changes |
| Monitor capacity, dependencies, errors, and service health | Application maintainer / IT | Agreed schedule and alerts |
| Update runbook and transfer ownership | Primary and backup maintainers | Releases and personnel changes |

CSV exports are not complete database backups. GitHub does not back up the live databases or ignored secrets. Store recovery material through approved institutional mechanisms.

For publication, create a versioned data package with a dictionary, methods/provenance, units, use terms, and a persistent identifier from the chosen repository. Prepare repository-specific metadata, including EML where required, separately. The portal supports ongoing collaboration; public archival releases require an additional documented workflow.

## Adapting the portal to another study

For a freshwater-monitoring project, define `sites` and `observations` keyed by `site_id` and sampling event/date. Include explicit temperature and dissolved-oxygen units. This is an illustrative design, not a distributed/tested demo.

| Area | Example adaptation | Work involved |
| --- | --- | --- |
| Preparation | Standardize site identifiers, dates, units, and missing values; retain raw inputs and QC reports | Potentially substantial legacy-data work |
| Flat-file browser | Create tables and set `TABLE_OPTIONS=sites,observations` | Configuration after schema preparation |
| Select and Filter | Add `observations` to `CORE_TABLES`; revise keys, labels, and optional joins to use `site_id` | Python/SQL changes and validation |
| Analysis | Choose appropriate numeric variables and review repeated-measure/model assumptions | Scientific review and test cases |
| Map | Set `MAP_TABLE=sites`; map coordinate/locality fields; replace oak references and identifier search | Targeted Python/SQL changes |
| Upload | Set `UPLOAD_TEMPLATE_TABLES=observations`; use its physical schema or define a metadata mapping; prepare holding tables | Database/configuration work plus validation and review rules |
| Permissions and hosting | Configure account tiers, server-side policy, hosting, recovery, and ownership | IT/developer coordination and ongoing maintenance |

Start with a small validated dataset and browsing/export, then add joins, maps, and submissions as their behavior is verified. Data stewardship requires familiarity with the science and tabular data; callback/join adaptation requires Python/SQL skills; shared operation requires host/database/identity administration. Actual effort depends on data condition, available services, and staff experience; no measured time estimate is claimed.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Empty flat-file dropdown | Root `.env`, `TABLE_OPTIONS`, working directory, and restart after configuration changes |
| Upload choices differ from browser tables | `UPLOAD_TEMPLATE_TABLES` is independent of `TABLE_OPTIONS` |
| Template/schema unavailable | Mapped metadata table exists, is readable, contains rows, and has `Variable`, `Type`, `Required`, `Description` |
| Generated workbook later fails header-order validation | Check metadata ordering; the current metadata query has no explicit ordering |
| Excel support missing | Install requirements.txt in the active environment; it includes `openpyxl` |
| Submission fails or is absent from source data | Check `DB_UPLOAD_*`, holding-table permissions/schema, and staging database. Successful submissions intentionally await external review/promotion |
| Public credential fallback warning | Configure all four `DB_PUBLIC_*` settings and test routing/permissions; map reads still use standard credentials |
| Driver not found or database inaccessible | Verify the system ODBC driver, network/VPN, login, database permissions, and connection URL/certificate handling |
| Map filters have no expected effect | Verify matching availability/map columns and supported filters; inspect study-specific year/locality logic |
| Flat-file export is larger than the preview | Expected: export includes every row and column; use Select and Filter for supported subset exports |
| Row ranges change between requests | Shared row retrieval uses `ORDER BY (SELECT NULL)`; add a stable unique-key ordering when reproducibility requires it |
| Logout returns to a local address | Update both hard-coded return routes in `app.py` and Auth0 settings |
| Large view/export is slow | Reduce result sizes and review query/index design, server memory, browser memory, and concurrency |

## Companion data-preparation workflow

The manuscript review refers to `data_management_public`, a separate R-script repository whose URL has not been established here. This repository contains the Python portal; it does not establish the R scripts' execution order. `QPLAD_data_management/` is ignored by [.gitignore](.gitignore) and is not a distributed setup dependency.

To document the complete workflow, the companion repository needs a verified link/version, a README, representative non-sensitive inputs/outputs, and a script inventory. For each script provide its purpose, inputs and schema, outputs, R/package dependencies, execution order, adaptation points, and whether it appends/replaces/deletes data. Put this information in script headers as well as the inventory.

The conceptual sequence is **inventory -> standardize -> validate -> load approved tables -> verify -> use the portal**. It is not a verified order for unidentified R files. Link the actual guide here and in the manuscript after checking those files.

For manuscript readers, Steps 1 and 3 explain data organization and storage, Steps 4–7 explain portal setup/use, and Step 8 explains operation and continuity. These numbered technical instructions can be referenced separately from the conceptual framework.
