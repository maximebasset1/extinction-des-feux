"""La publication sur GitHub Pages survit à un refus passager du service (erreur 500 du 25 novembre 2026)."""
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "mise-a-jour.yml"


def test_publication_is_retried_once_after_a_pages_failure():
    publication = WORKFLOW.read_text(encoding="utf-8").split("\n  publication:\n", 1)[1]
    etapes = publication.split("\n    steps:\n", 1)[1].split("\n      - ")
    assert len(etapes) == 3
    premier, attente, second = etapes
    # le premier essai peut échouer sans arrêter la tâche ; le second, lui, doit pouvoir la faire échouer
    assert "uses: actions/deploy-pages@v4" in premier and "continue-on-error: true" in premier
    assert "if: steps.essai1.outcome == 'failure'" in attente and "sleep 120" in attente
    assert "uses: actions/deploy-pages@v4" in second and "if: steps.essai1.outcome == 'failure'" in second
    assert "continue-on-error" not in second
    assert "url: ${{ steps.essai2.outputs.page_url || steps.essai1.outputs.page_url }}" in publication
