from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from accounts.models import CustomUser

@login_required
def dashboard(request):
    users = CustomUser.objects.all()
    context = {'users': users}
    return render(request, 'dashboard.html', context)

@login_required
def personnel(request):
    users = CustomUser.objects.all().order_by("first_name", "last_name")
    return render(request, 'personnel.html', {"users": users})