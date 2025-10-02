from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from accounts.models import CustomUser

@login_required
def dashboard(request):
    users = CustomUser.objects.all()
    context = {'users': users}
    return render(request, 'dashboard.html', context)