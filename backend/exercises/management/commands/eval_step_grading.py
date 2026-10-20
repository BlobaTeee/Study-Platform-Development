"""Run the practice grader on a ProcessBench sample, a few items at a time.

    python manage.py eval_step_grading --n 40
    python manage.py eval_step_grading --split handmade     # outside maths

Each problem goes through the app's own path: a rubric as for a student's
own problem, then the grade. One line per item is appended to
ml_pipeline/reports/step_grading_<split>.jsonl; items already there are
skipped, so a run stopped by the daily quota carries on the next day. The
metrics are worked out in ml_pipeline/notebooks/09_step_grading.ipynb.
Nothing is written to the database.
"""
import json

from django.core.management.base import BaseCommand

from exercises.models import Exercise
from exercises.services import grading, problems
from exercises.services.common import PracticeUnavailable
from ml_pipeline import step_grading

RUBRICS = step_grading.REPORTS / 'step_grading_rubrics.json'


class Command(BaseCommand):
    help = 'Grade a ProcessBench sample with the practice grader (resumable).'

    def add_arguments(self, parser):
        parser.add_argument('--n', type=int, default=40, help='ProcessBench sample size (handmade: all)')
        parser.add_argument('--split', default='gsm8k', help="a ProcessBench split, or 'handmade'")
        parser.add_argument('--out', default='', help='results name, to measure a changed grader beside the old one')

    def handle(self, *args, n, split, out, **options):
        results = step_grading.results_path(out or split)
        handmade = split == 'handmade'
        done = {r['id'] for r in step_grading.read_results(results)}
        rubrics = json.loads(RUBRICS.read_text()) if RUBRICS.exists() else {}
        items = step_grading.load(split)
        # The hand-made set is small and graded whole, in file order.
        sample = items if handmade else step_grading.balanced_sample(items, n)
        todo = [i for i in sample if i['id'] not in done]
        self.stdout.write(f'{len(done)} graded already, {len(todo)} to go')
        results.parent.mkdir(parents=True, exist_ok=True)

        for item in todo:
            try:
                if item['problem'] not in rubrics:
                    rubric = problems.own_rubric(item['problem'])
                    rubrics[item['problem']] = rubric
                    RUBRICS.write_text(json.dumps(rubrics, ensure_ascii=False, indent=1))
                rubric = rubrics[item['problem']]
                unsaved = Exercise(prompt=rubric['prompt'], reference=rubric['reference'])
                result = grading.grade(unsaved, item['steps'])
            except problems.IncompleteProblem as exc:
                result = {'verdict': 'refused', 'detail': str(exc)}
            except PracticeUnavailable as exc:
                self.stdout.write(f'stopped: {exc}')
                break
            pred = (step_grading.to_label(result, len(item['steps']), stops_short=handmade)
                    if result['verdict'] != 'refused' else None)
            line = {'id': item['id'], 'label': item['label'], 'pred': pred, 'n_steps': len(item['steps']),
                    'result': result}
            if handmade:
                line.update(subject=item['subject'], lang=item['lang'], error_type=item['error_type'])
            with results.open('a') as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + '\n')
            self.stdout.write(f"{item['id']}: gold {item['label']} pred {pred}")
