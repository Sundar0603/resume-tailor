import sys
import json
from pathlib import Path
sys.path.insert(0, '.')

from src.parser.resume_parser import ResumeParser

OUTPUT_FILE = Path('resume_output.txt')
_output_lines = []


def log(text=''):
    print(text)
    _output_lines.append(text)


def print_resume(resume):
    text = json.dumps(resume.model_dump(), indent=2)
    log(text)
    log()


def flush_output():
    OUTPUT_FILE.write_text('\n'.join(_output_lines), encoding='utf-8')
    print(f'\nFull output written to {OUTPUT_FILE.resolve()}')


parser = ResumeParser()

# cybersecurity
resume = parser.parse('content/cybersecurity_resume.md')
log('=== cybersecurity ===')
log('metadata.resume : ' + resume.metadata.resume)
log('contact.name    : ' + resume.contact.name)
log('len(skills)     : ' + str(len(resume.skills)))
log('len(experiences): ' + str(len(resume.experiences)))
log('len(projects)   : ' + str(len(resume.projects)))
log('len(education)  : ' + str(len(resume.education)))
assert resume.metadata.resume == 'cybersecurity'
assert resume.contact.name == 'Sundar S'
assert len(resume.skills) > 0
assert len(resume.experiences) == 2, f'expected 2, got {len(resume.experiences)}'
assert len(resume.projects) == 2, f'expected 2, got {len(resume.projects)}'
assert len(resume.education) == 1, f'expected 1, got {len(resume.education)}'
print_resume(resume)
log('PASSED')
log()

# backend
resume2 = parser.parse('content/backend_resume.md')
log('=== backend ===')
log('metadata.resume : ' + resume2.metadata.resume)
log('contact.name    : ' + resume2.contact.name)
log('len(skills)     : ' + str(len(resume2.skills)))
log('len(experiences): ' + str(len(resume2.experiences)))
log('len(projects)   : ' + str(len(resume2.projects)))
log('len(education)  : ' + str(len(resume2.education)))
assert resume2.metadata.resume == 'backend'
assert resume2.contact.name == 'Sundar S'
assert len(resume2.skills) > 0
assert len(resume2.experiences) == 2, f'expected 2, got {len(resume2.experiences)}'
assert len(resume2.projects) == 2, f'expected 2, got {len(resume2.projects)}'
assert len(resume2.education) == 1, f'expected 1, got {len(resume2.education)}'
print_resume(resume2)
log('PASSED')
log()

# fullstack
resume3 = parser.parse('content/fullstack_resume.md')
log('=== fullstack ===')
log('metadata.resume : ' + resume3.metadata.resume)
log('contact.name    : ' + resume3.contact.name)
log('len(skills)     : ' + str(len(resume3.skills)))
log('len(experiences): ' + str(len(resume3.experiences)))
log('len(projects)   : ' + str(len(resume3.projects)))
log('len(education)  : ' + str(len(resume3.education)))
assert resume3.metadata.resume == 'fullstack'
assert resume3.contact.name == 'Sundar S'
assert len(resume3.skills) > 0
assert len(resume3.experiences) == 2, f'expected 2, got {len(resume3.experiences)}'
assert len(resume3.projects) == 2, f'expected 2, got {len(resume3.projects)}'
assert len(resume3.education) == 1, f'expected 1, got {len(resume3.education)}'
print_resume(resume3)
log('PASSED')
log()

log('=' * 50)
log('ALL CHECKS PASSED')

flush_output()
