"""Normalize reviewer options while keeping display names separate from IDs."""


def reviewer_options(users):
    options = []

    def visit(node):
        if isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            for key in ('content', 'records', 'list', 'data'):
                if isinstance(node.get(key), (list, dict)):
                    visit(node[key])
            user_id = next((str(node[k]) for k in ('id', 'userId', 'reviewUserId', 'value')
                            if node.get(k) is not None and str(node[k]).strip()), '')
            job = str(node.get('jobNo') or node.get('job_no') or '').strip()
            name = str(node.get('realName') or node.get('userName') or node.get('name') or '').strip()
            label = str(node.get('label') or node.get('displayName') or '').strip()
            if not label:
                label = name if not job or name.startswith(job) else job + name
            if user_id and label:
                options.append((label, user_id, job))

    visit(users)
    return list(dict.fromkeys(options))


def resolve_review_user_id(users, selection):
    selection = ''.join(selection.split())
    # Do not silently choose between two different IDs with the same name.
    matches = {user_id for label, user_id, job in reviewer_options(users)
               if selection and selection in (''.join(label.split()), job)}
    return matches.pop() if len(matches) == 1 else None
