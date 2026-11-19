"""macOS Keychain access scoped to this mailbox; never prints a secret."""
import ctypes as c
import sys

SERVICE = b'fr.jalauris.retention.imap'
ACCOUNT = b'solution@jalauris.fr'


class KeychainError(RuntimeError):
    """Fixed diagnostic text; never contains a secret."""



def api(interactive):
    if sys.platform != 'darwin':
        raise KeychainError('Le Trousseau macOS est requis')
    lib = c.CDLL('/System/Library/Frameworks/Security.framework/Security')
    ptr, uint = c.c_void_p, c.c_uint32
    signatures = {
        'SecKeychainSetUserInteractionAllowed': [c.c_bool],
        'SecKeychainAddGenericPassword': [ptr, uint, c.c_char_p, uint, c.c_char_p, uint, ptr, ptr],
        'SecKeychainFindGenericPassword': [ptr, uint, c.c_char_p, uint, c.c_char_p, c.POINTER(uint), c.POINTER(ptr), c.POINTER(ptr)],
        'SecKeychainItemFreeContent': [ptr, ptr],
        'SecKeychainItemModifyAttributesAndData': [ptr, ptr, uint, ptr],
    }
    for name, args in signatures.items():
        method = getattr(lib, name)
        method.argtypes, method.restype = args, c.c_int32
    if lib.SecKeychainSetUserInteractionAllowed(interactive) != 0:
        raise KeychainError('Trousseau indisponible')
    return lib


def save(password):
    lib = api(True)
    data = password.encode('utf-8')
    status = lib.SecKeychainAddGenericPassword(None, len(SERVICE), SERVICE, len(ACCOUNT), ACCOUNT, len(data), data, None)
    if status == -25299:  # existing item, update only this service/account
        item = c.c_void_p()
        status = lib.SecKeychainFindGenericPassword(None, len(SERVICE), SERVICE, len(ACCOUNT), ACCOUNT, None, None, c.byref(item))
        if status == 0:
            try:
                status = lib.SecKeychainItemModifyAttributesAndData(item, None, len(data), data)
            finally:
                cf = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
                cf.CFRelease.argtypes = [c.c_void_p]
                cf.CFRelease.restype = None
                cf.CFRelease(item)
    if status != 0:
        raise KeychainError('Enregistrement dans le Trousseau refusé')


def read(interactive=False):
    lib = api(interactive)
    size, data = c.c_uint32(), c.c_void_p()
    status = lib.SecKeychainFindGenericPassword(None, len(SERVICE), SERVICE, len(ACCOUNT), ACCOUNT, c.byref(size), c.byref(data), None)
    if status != 0:
        raise KeychainError('Mot de passe indisponible dans le Trousseau ; relancer la configuration localement')
    try:
        return c.string_at(data, size.value).decode('utf-8')
    finally:
        lib.SecKeychainItemFreeContent(None, data)
