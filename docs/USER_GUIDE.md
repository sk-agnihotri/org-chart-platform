# Org Chart Inference Platform

## What the app does

The app ranks possible employee-manager relationships from observable employee attributes and a title taxonomy. Scores are weighted evidence rankings, not calibrated probabilities or verified reporting facts. Synthetic ground truth is reserved for the Evaluation tab and is never used to infer relationships.

## Explore a company

- **Org Chart:** Explore accepted inferred links. Filter by department, designation, evidence score, and employee name or title. Use **Clear chart filters** if the current selection produces no employees.
- **Employee Explorer:** Inspect normalized titles, inferred managers, status, and reason. Select a department and designations to scope the CSV export. The export includes company and dataset-date context.
- **Relationship evidence:** Select an employee to inspect the top candidate, available alternative, scoring signals, score margin, and inferred path to the root. Evidence scores rank candidates; they do not represent calibrated confidence.

## Review and interpret

- **Review Queue:** Includes ambiguous and unresolved relationships and accepted relationships scoring below 0.85. Filter by review reason, hide reviewed rows, and mark an item reviewed. Review marks are held in Streamlit session state and do not persist across sessions, users, or app restarts.
- **Company Insights:** Summarizes accepted links, inferred reporting depth, unresolved links, and review prompts. Prompts flag missing titles or departments, unresolved relationships, and more than ten accepted direct reports for one manager. They are cues to inspect data, not diagnoses of organizational quality.
- **Evaluation:** Uses synthetic ground truth only to calculate evaluation metrics. It is not a real-world accuracy guarantee.

## Compare dataset versions

Before replacing observable CSV files, snapshot the current version:

```powershell
python scripts\snapshot_dataset.py v1
```

Use a unique label for every version. Commit the created `data/snapshots/<label>/` directory and the new observable dataset to the feature branch, then deploy that branch. The **Compare Versions** tab reports employee arrivals and departures, profile changes, and manager changes inferred under the current algorithm. An inferred manager change is a difference between model suggestions, not a verified reporting change. Only snapshots committed in the deployed branch are available to compare.

Snapshots contain observable company, employee, taxonomy, and metadata CSVs. They do not include ground truth or evaluation labels.

## Data and persistence boundaries

- Production is read-only for employee records; add/remove operations are intentionally not included.
- CSV updates made outside source control are not a durable shared database. Commit updated datasets and snapshots to Git to deploy them.
- Review marks are temporary session state. Persistent multi-user review history requires a database or other durable shared store.
- The current dataset metadata has no as-of date, so exports and views show “not recorded in dataset metadata” until one of `dataset_date`, `generated_at_utc`, or `data_as_of` is supplied in `data/dataset_metadata.csv`.
- Structural metrics are heuristic prompts; validate their interpretation with domain experts before using them for decisions.
