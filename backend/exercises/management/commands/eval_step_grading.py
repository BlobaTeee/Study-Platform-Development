"""Run the practice grader on a ProcessBench sample, a few items at a time.

    python manage.py eval_step_grading --n 40

Each problem goes through the app's own path: a rubric as for a student's
own problem, then the grade. One line per item is appended to
ml_pipeline/reports/step_grading_gsm8k.jsonl; items already there are
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

RUBRICS = step_grading.RESULTS.with_name('step_grading_rubrics.json')


class Command(BaseCommand):
    help = 'Grade a ProcessBench sample with the practice grader (resumable).'

    def add_arguments(self, parser):
        parser.add_argument('--n', type=int, default=40)
        parser.add_argument('--split', default='gsm8k')

    def handle(self, *args, n, split, **options):
        done = {r['id'] for r in step_grading.read_results()}
        rubrics = json.loads(RUBRICS.read_text()) if RUBRICS.exists() else {}
        todo = [i for i in step_grading.balanced_sample(step_grading.load(split), n) if i['id'] not in done]
        self.stdout.write(f'{len(done)} graded already, {len(todo)} to go')
        step_grading.RESULTS.parent.mkdir(parents=True, exist_ok=True)

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
            pred = step_grading.to_label(result, len(item['steps'])) if result['verdict'] != 'refused' else None
            line = {'id': item['id'], 'label': item['label'], 'pred': pred, 'n_steps': len(item['steps']),
                    'result': result}
            with step_grading.RESULTS.open('a') as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + '\n')
            self.stdout.write(f"{item['id']}: gold {item['label']} pred {pred}")
