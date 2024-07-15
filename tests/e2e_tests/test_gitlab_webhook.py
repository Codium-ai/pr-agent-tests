import os
import re
import time
from datetime import datetime

import gitlab

from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider
from pr_agent.log import setup_logger, get_logger

log_level = os.environ.get("LOG_LEVEL", "INFO")
setup_logger(log_level)
logger = get_logger()

new_content = """\
from pr_agent import cli
from pr_agent.config_loader import get_settings


def main():
    # Fill in the following values
    provider = "github"  # GitHub provider
    user_token = "..."  # GitHub user token
    openai_key = "ghs_afsdfasdfsdf"  # OpenAI key
    pr_url = "..."  # PR URL, for example 'https://github.com/Codium-ai/pr-agent/pull/809'
    command = "/improve"  # Command to run (e.g. '/review', '/describe', 'improve', '/ask="What is the purpose of this PR?"')

    # Setting the configurations
    get_settings().set("CONFIG.git_provider", provider)
    get_settings().set("openai.key", openai_key)
    get_settings().set("github.user_token", user_token)

    # Run the command. Feedback will appear in GitHub PR comments
    output = cli.run_command(pr_url, command)

    print(output)

if __name__ == '__main__':
    main()
"""


def test_e2e_run_github_app():
    # GitLab setup
    GITLAB_URL = "https://gitlab.com"
    GITLAB_TOKEN = get_settings().gitlab.PERSONAL_ACCESS_TOKEN
    gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
    repo_url = 'codiumai/pr-agent-tests'
    project = gl.projects.get(repo_url)

    base_branch = "main"  # or any base branch you want
    new_branch = f"github_app_e2e_test-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"

    try:
        # Create a new branch from the base branch
        source_branch = project.branches.get(base_branch)
        logger.info(f"Creating a new branch {new_branch} from {base_branch}")
        project.branches.create({'branch': new_branch, 'ref': base_branch})

        # Get the file you want to edit
        file_path = "pr_agent/cli_pip.py"
        file = project.files.get(file_path=file_path, ref=base_branch)
        # content = file.decode()

        # Update the file content
        logger.info(f"Updating the file {file_path}")
        commit_message = "update cli_pip.py"
        file.content = new_content
        file.save(branch=new_branch, commit_message=commit_message)

        # Create a merge request
        logger.info(f"Creating a merge request from {new_branch} to {base_branch}")
        mr = project.mergerequests.create({
            'source_branch': new_branch,
            'target_branch': base_branch,
            'title': new_branch,
            'description': "update cli_pip.py"
        })
        logger.info(f"Merge request created: {mr.web_url}")


        # check the PR every minute, up to a limit of 5 minutes, to see if we got all the tool results
        PR_HEADER_START_WITH = '### **User description**\nupdate cli_pip.py\n\n\n___\n\n### **PR Type**'
        REVIEW_START_WITH = '## PR Reviewer Guide 🔍\n\n<table>\n<tr><td>⏱️&nbsp;<strong>Estimated effort to review</strong>:'
        IMPROVE_START_WITH_REGEX_PATTERN = r'^## PR Code Suggestions ✨\n\n<!-- [a-z0-9]+ -->\n\n<table><thead><tr><td>Category</td>'

        NUM_MINUTES = 5
        for i in range(NUM_MINUTES):
            logger.info(f"Waiting for the MR to get all the tool results...")
            time.sleep(60)
            logger.info(f"Checking the MR {mr.web_url} after {i + 1} minute(s)")
            mr = project.mergerequests.get(mr.iid)
            mr_header_body = mr.description
            comments = mr.notes.list()[::-1]
            if len(comments) == 3: # "changed the description" is received as the first comment
                comments_body = [comment.body for comment in comments]
                if 'Work in progress' in comments_body[1] or 'Work in progress' in comments_body[2]:
                    continue
                assert mr_header_body.startswith(PR_HEADER_START_WITH), "DESCRIBE feedback is invalid"
                assert comments_body[1].startswith(REVIEW_START_WITH), "REVIEW feedback is invalid"
                assert re.match(IMPROVE_START_WITH_REGEX_PATTERN, comments_body[2]), "IMPROVE feedback is invalid"
                break
            else:
                logger.info(f"Waiting for the MR to get all the tool results. {i + 1} minute(s) passed")
        else:
            assert False, f"After {NUM_MINUTES} minutes, the MR did not get all the tool results"

        # delete the branch
        logger.info(f"Deleting the branch {new_branch}")
        project.branches.delete(new_branch)
        logger.info(f"Succeeded in running e2e test for GitLab app on the MR {mr.web_url}")
    except Exception as e:
        logger.error(f"Failed to run e2e test for GitHub app: {e}")
        logger.info(f"Deleting the branch {new_branch}")
        project.branches.delete(new_branch)
        assert False


if __name__ == '__main__':
    test_e2e_run_github_app()
