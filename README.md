# Student Manager: Cloud Lab Part II (PaaS)

A small Flask + Firestore CRUD app that students deploy to Google App Engine.
Students do not edit the code; they only change `app.yaml`. The lab handout
walks them through deploying, using, observing and versioning it.

## Files

| File               | Purpose                                                                                               |
| -------------------| ------------------------------------------------------------------------------------------------------|
| `main.py`          | Routes for list, add, edit, delete and reset; seed-on-first-run logic                                 |
| `seed_data.py`     | The 12 sample students                                                                                |
| `templates/`       | `base.html` (layout, color band, version/instance panel), `index.html`, `form.html`, `not_found.html` |
| `app.yaml`         | Runtime, instance class, scaling limits, and the settings students change                             |
| `requirements.txt` | Pinned dependencies                                                                                   |
| `.gcloudignore`    | Keeps local clutter out of deployments                                                                |

## Settings (env_variables in app.yaml)

| Variable              | Default           | Used for                                                                                                |
| ----------------------| ------------------| --------------------------------------------------------------------------------------------------------|
| `APP_TITLE`           | `Student Manager` | Page title; students add their name (Step 4)                                                            |
| `APP_COLOR`           | `#2563eb`         | Header color; students change it for version v2 (Step 8). Text color adjusts automatically for contrast |
| `STUDENTS_COLLECTION` | `students`        | Firestore collection name                                                                               |

The header shows `GAE_VERSION` and `GAE_INSTANCE`, which App Engine sets on its own.
This is what makes traffic splitting and instance changes visible to students.

## How seeding works

On the first request, the app tries to create a marker document at
`_lab_meta/seed`. Only the first instance to do so succeeds, and it writes
the sample students with fixed IDs (`seed-01` to `seed-12`). Later instances
see the marker and skip seeding. This means:

- Two instances starting together never load the data twice.
- Records a student deletes are not brought back by a later instance or a new version.
- **Reset demo data** deletes the whole collection and writes the samples again.

The client is created on first use, not at import, so the app still starts if
the Firestore database hasn't been created yet; the error appears on the first
request instead, in the logs.

## Running locally (instructors only)

Using the Firestore emulator (needs Java):

```
gcloud emulators firestore start --host-port=localhost:8086
# in another terminal
export FIRESTORE_EMULATOR_HOST=localhost:8086 GOOGLE_CLOUD_PROJECT=demo-lab
pip install -r requirements.txt
python main.py        # http://127.0.0.1:8080
```

## Cost guardrails

`instance_class: F1`, `min_instances: 0` and `max_instances: 2` keep each
student's app inside App Engine's free instance hours. Firestore usage for this
lab is a tiny fraction of its daily free quota.
