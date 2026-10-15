"""Bind empirical artifacts to source bundles and reproduce the transparent baseline."""
from hashlib import sha256
import json
from pathlib import Path


def json_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def verify_artifacts(dataset, evaluation, *, base_dir: Path):
    """Reject stale/mismatched artifacts. This verifies reproducibility, not human quality."""
    from corpus_v10 import audit
    from oracle_dataset_v10 import build_dataset_from_paths
    from representation_policy_v10 import OracleRepresentationPolicy, evaluate_policy
    failures = []
    body = {k: v for k, v in dataset.items() if k != "dataset_sha256"}
    identity = json_hash(body)
    if dataset.get("dataset_sha256") != identity or evaluation.get("dataset_sha256") != identity:
        failures.append("dataset/evaluation hash binding missing or mismatched")
    sources = dataset.get("source_bundles", [])
    if not sources:
        return failures + ["source bundle manifest missing"]
    paths = []
    for source in sources:
        path = base_dir / source["path"]
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            failures.append("source bundle missing or changed: " + source["path"])
        paths.append(path)
    if failures:
        return failures
    try:
        rebuilt = build_dataset_from_paths(paths, eval_fraction=dataset["parameters"]["eval_fraction"],
                                           tolerance_s=dataset["parameters"]["consensus_tolerance_s"],
                                           min_votes=dataset["parameters"]["min_votes"])
        if rebuilt["splits"] != dataset["splits"]:
            failures.append("dataset splits do not reproduce from source bundles")
        if any(dataset["stats"].get(k) != v for k, v in rebuilt["stats"].items()):
            failures.append("dataset summary does not reproduce from source bundles")
        quality = audit(paths)
        if quality["errors"] or dataset["stats"].get("empirical_eligible_talks") != quality["eligible_talks"]:
            failures.append("corpus eligibility does not reproduce from source bundles")
        if dataset["stats"].get("non_fixture_talks") != quality["non_fixture_talks"]:
            failures.append("non-fixture talk count does not reproduce from source bundles")
        policy = OracleRepresentationPolicy.fit(rebuilt["splits"]["train"])
        if evaluation.get("policy_sha256") != json_hash(policy.artifact):
            failures.append("policy does not reproduce from the declared training split")
        expected = evaluate_policy(policy, rebuilt["splits"]["eval"])
        if any(evaluation.get(k) != v for k, v in expected.items()):
            failures.append("evaluation rows/metrics do not reproduce on the held-out split")
    except (ValueError, TypeError, KeyError, OSError) as e:
        failures.append(f"artifact reproduction failed: {e}")
    return failures
