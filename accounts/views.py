
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import UserProfileForm

@login_required
def edit_profile(request):
    user = request.user
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect('account')   # keep the same page or change to another view
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserProfileForm(instance=user)

    return render(request, 'accounts/userAccount.html', {'form': form})

@login_required
def redirect_user(request):
    user = request.user
    
    if user.role in ["manager", "admin"]:
        return redirect('dashboard')
    else:
        return redirect("profile")