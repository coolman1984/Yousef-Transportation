"""Stable translation keys for the messages the server sends to the screens (I7).

The server still writes its messages in English (they go to the logs and to scripts), but every answer that reaches a person also
carries `key` and `vars`, and the page shows the text of that key in the language of the screen (js/i18n/en.js, ar.js: `err.*`,
`autherr.*`). One table, so adding a message is one line here and two lines in the dictionaries. `tests/test_errors.py` checks that
every key exists in both dictionaries and that the common messages are covered.
"""
import re

# (pattern of the English message, key). Named groups become the `vars` of the message.
CATALOG = [
    (r'^Wrong user name or password\.$', 'autherr.wrong'),
    (r'^This account is locked for (?P<mins>\d+) more minute', 'autherr.locked'),
    (r'^Too many wrong passwords\. The account is locked for (?P<mins>\d+) minutes', 'autherr.lockedNow'),
    (r'^This account is disabled', 'autherr.disabled'),
    (r'^Too many (wrong )?attempts', 'autherr.tooMany'),
    (r'^Please log in\.?$', 'err.signIn'),
    (r'^The password must have at least (?P<n>\d+) characters', 'autherr.pwShort'),
    (r'^The password is too long', 'autherr.pwLong'),
    (r'^This password is too easy', 'autherr.pwEasy'),
    (r'^The password must not contain', 'autherr.pwContains'),
    (r'^The password must contain letters', 'autherr.pwLetters'),
    (r'^The current password is wrong', 'autherr.pwCurrentWrong'),
    (r'^The new password must be different', 'autherr.pwSame'),
    (r'^User name: 3-32', 'autherr.username'),
    (r'^Enter the full name', 'autherr.fullname'),
    (r'^The administrator account already exists', 'autherr.adminExists'),
    (r'^The first administrator account can only be created', 'err.firstAdminLocal'),
    (r'^This link does not work any more', 'autherr.linkDead'),
    (r'^This user no longer exists', 'autherr.noUser'),
    (r'^The user name "(?P<name>.*)" is already used', 'autherr.userTaken'),
    (r'^At least one active (person|user) must keep the right', 'autherr.lastAdmin'),
    (r'^You cannot (disable yourself|delete your own account)', 'autherr.self'),
    (r'^You have this profile yourself', 'autherr.self'),
    (r'^People (with administrator rights|who log in with a personal link)', 'autherr.linkAdmin'),
    (r'^Administrator accounts must log in with their password', 'autherr.linkAdmin'),
    (r'^The system is still starting', 'err.starting'),
    (r'^For security, please change your password', 'autherr.pwOld'),
    (r'^Please change your temporary password first', 'err.mustChange'),
    (r'^Only an administrator can', 'err.adminOnly'),
    (r'^Only on this PC itself', 'err.localOnly'),
    (r'^For safety, .* on this PC itself', 'err.localOnly'),
    (r'^Request from another web site was blocked', 'err.crossSite'),
    (r'^This PC only accepts connections from the office network', 'err.network'),
    (r'^This is not one of this PC', 'err.host'),
    (r'^Request too large', 'err.tooLarge'),
    (r'^Invalid request length', 'err.badRequest'),
    (r'^Not found$', 'err.notFound'),
    (r'^File not found$', 'err.notFound'),
    (r'^The request must be a JSON object', 'err.badRequest'),
    (r'^Trip not found', 'err.tripNotFound'),
    (r'^Write the reason for the change', 'err.reason'),
    (r'^Choose a trip category', 'err.chooseCategory'),
    (r'^Nothing to save', 'err.nothingToSave'),
    (r'^Nothing changed', 'err.nothingChanged'),
    (r'^Choose the month', 'err.chooseMonth'),
    (r'^This trip is locked', 'err.tripLocked'),
    (r'^You can only change the trip categories assigned to you', 'err.categoryLimited'),
    (r'^You are limited to certain trip categories', 'err.categoryLimited'),
    (r'^This PC needs a decision first', 'err.moved'),
    (r'^The licence', 'err.licence'),
    (r'^\w+: write a whole number', 'err.wholeNumber'),
    (r'^date: write the date like', 'err.badDate'),
    (r'^date: more than (?P<days>\d+) days away', 'err.dateFar'),
    (r'^endKm: the end odometer cannot be lower', 'err.kmOrder'),
    (r'^\w+: write the time like', 'err.badTime'),
    (r'^endAt: the end time cannot be before', 'err.timeOrder'),
    (r'^\w+: at most (?P<n>\d+) characters', 'err.tooLong'),
    (r'^status: not a known status', 'err.badStatus'),
    (r'^A cancelled trip cannot be opened again', 'err.cancelledFinal'),
    (r'^A closed trip can only be cancelled', 'err.closedFinal'),
    (r'^General Affairs declined this trip', 'err.gaDeclined'),
    (r'^This (vehicle|driver|category|department|person) is used by (?P<n>\d+) trip', 'err.inUse'),
    (r'^\w+: write a number that is not below zero', 'err.negative'),
    (r'^Another (category|department|vehicle|driver|place|person) already has this', 'err.duplicate'),
    (r'^This person is already in the list', 'err.dupPerson'),
    (r'^Kilometres must be a positive number', 'err.kmPositive'),
    (r'^Only a finished trip can be marked as reviewed', 'err.notFinished'),
    (r'^Only a trip that has not left yet can be started', 'err.cannotStart'),
    (r'^A cancelled trip cannot be closed', 'err.cancelledClose'),
    (r'^Write both odometer readings and both times', 'err.closeMissing'),
    (r'^The clock of this PC is off by (?P<mins>\d+) minute', 'err.clockOff'),
    (r'^The mailbox refused this PC', 'err.mailboxSecret'),
    (r'^The mailbox saw this request twice', 'err.mailboxReplay'),
]
_COMPILED = [(re.compile(p), k) for p, k in CATALOG]
KEYS = sorted({k for _, k in CATALOG} | {'err.needPerm', 'err.notAllowedTo', 'err.server', 'err.busy', 'err.limitedPerm'})


def key_for(message):
    """(key, vars) for an English message, or ('', {}) when the message has no translation key yet."""
    msg = str(message or '')
    for rx, key in _COMPILED:
        m = rx.search(msg)
        if m:
            return key, {k: v for k, v in m.groupdict().items() if v is not None}
    return '', {}
