import subprocess

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import HttpResponse

from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view

from .models import PendingAction
from agents.models import Agent
from .serializers import PendingActionSerializer
from agents.serializers import AgentHostnameSerializer
from .tasks import cancel_pending_action_task


@api_view()
def agent_pending_actions(request, pk):
    action = PendingAction.objects.filter(agent__pk=pk)
    return Response(PendingActionSerializer(action, many=True).data)


@api_view()
def all_pending_actions(request):
    actions = PendingAction.objects.all()
    return Response(PendingActionSerializer(actions, many=True).data)


@api_view(["DELETE"])
def cancel_pending_action(request):
    action = get_object_or_404(PendingAction, pk=request.data["pk"])
    data = PendingActionSerializer(action).data
    cancel_pending_action_task.delay(data)
    action.delete()
    return Response(
        f"{action.agent.hostname}: {action.description} will be cancelled shortly"
    )


@api_view()
def debug_log(request, mode, hostname, order):
    log_file = settings.LOG_CONFIG["handlers"][0]["sink"]

    agents = Agent.objects.all()
    agent_hostnames = AgentHostnameSerializer(agents, many=True)

    switch_mode = {
        "info": "INFO",
        "critical": "CRITICAL",
        "error": "ERROR",
        "warning": "WARNING",
    }
    level = switch_mode.get(mode, "INFO")

    if hostname == "all" and order == "latest":
        cmd = f"grep -h {level} {log_file} | tac"
    elif hostname == "all" and order == "oldest":
        cmd = f"grep -h {level} {log_file}"
    elif hostname != "all" and order == "latest":
        cmd = f"grep {hostname} {log_file} | grep -h {level} | tac"
    elif hostname != "all" and order == "oldest":
        cmd = f"grep {hostname} {log_file} | grep -h {level}"
    else:
        return Response("error", status=status.HTTP_400_BAD_REQUEST)

    contents = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        shell=True,
    )

    if not contents.stdout:
        resp = f"No {mode} logs"
    else:
        resp = contents.stdout

    return Response({"log": resp, "agents": agent_hostnames.data})


@api_view()
def download_log(request):
    log_file = settings.LOG_CONFIG["handlers"][0]["sink"]
    if settings.DEBUG:
        with open(log_file, "rb") as f:
            response = HttpResponse(f.read(), content_type="text/plain")
            response["Content-Disposition"] = "attachment; filename=debug.log"
            return response
    else:
        response = HttpResponse()
        response["Content-Disposition"] = "attachment; filename=debug.log"
        response["X-Accel-Redirect"] = "/private/log/debug.log"
        return response
