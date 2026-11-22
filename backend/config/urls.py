"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from pathlib import Path
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path, re_path
from django.views.static import serve

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR.parent / "frontend" / "dist"


def frontend_index(request):
    """Serves the production build of the React frontend if built, or status info."""
    index_file = DIST_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return HttpResponse(f.read())
    return JsonResponse({
        "status": "DealerOS Reconciliation API is running",
        "endpoints": {
            "disagreements": "/api/disagreements/?org=ORG-A",
            "orgs": "/api/orgs/",
        },
        "frontend_dev_server": "http://localhost:5173",
    })


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('reconcile.urls')),
    path('', frontend_index, name='frontend-root'),
    re_path(r'^assets/(?P<path>.*)$', serve, {'document_root': DIST_DIR / 'assets'}),
]
