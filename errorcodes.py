from enum import Enum


class ErrorCode(Enum):
    OK = 0
    UNSET = 1
    UNKNOWN = 2
    UNHANDLED_EXCEPTION = 3
    SERVER_ERROR = 4
    FILE_NOT_FOUND = 5
    FILE_INVALID = 6
    FILE_ALREADY_EXIST = 7
    BAD_ARGUMENTS = 8
    MISSING_KEY = 9
    INTERNAL_ERROR = 10

    @staticmethod
    def to_string(error_code):
        error_code_strings = \
            ['Ok',
             'Unset',
             'Unknown',
             'Unhandled exception',
             'ServerError',
             'File not found',
             'File invalid',
             'File already exist',
             'Bad arguments',
             'Missing key',
             'Internal error'
             ]

        return error_code_strings[error_code]
