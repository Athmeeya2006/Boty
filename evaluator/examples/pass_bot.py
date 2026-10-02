"""Protocol smoke-test bot; deliberately passes every turn."""


def act(observation):
    return [1, 0, 0, 0, 0]
