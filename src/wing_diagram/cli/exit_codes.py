import enum


class ExitCode(enum.IntEnum):
    # https://developer.atlassian.com/platform/nebulae/reference/plugins/#exit-codes
    # exit codes must be a valid 8-bit integer (that is, 0..255 inclusive)
    # There are no general conventions, but there is prior art, eg:
    # https://stackoverflow.com/questions/1101957/are-there-any-standard-exit-status-codes-in-linux
    # Exit codes above 127 are generally reserved.
    # Atlas CLI contract requires plugin (error) exit codes to start at 100.
    # https://developer.atlassian.com/platform/atlas-cli/devel/contract/exitcodes/
    OK = 0
    USER_INTERRUPT = 100
    ARGUMENT_ERROR = 101
    USER_ERROR = 102
    APPLICATION_ERROR = 103
    UNEXPECTED_ERROR = 105
