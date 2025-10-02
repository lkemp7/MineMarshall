from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from dashboard.models import Contractor

@login_required

def dashboard(request):
    contractors = Contractor.objects.all()
    context = {'contractors': contractors}
    return render(request, 'dashboard.html', context)