from django import template

register = template.Library()

@register.filter
def get_answer_for(answers_qs, question_id):
    # answers_qs is something like: existing_submission.answers.all()
    for a in answers_qs:
        if a.question_id == question_id:
            return a.value
    return ""
