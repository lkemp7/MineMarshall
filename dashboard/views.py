from django.http import HttpResponse
from django.template import loader
from django.contrib.auth.decorators import login_required
from dashboard.models import Contractor

@login_required

def dashboard(request):
    contractors = Contractor.objects.all()
    context = {'contractors': contractors}
    template = loader.get_template('dashboard.html')
    return HttpResponse(template.render(context = context))