#include "AppIdentity.h"

#include <QtGlobal>

#ifdef Q_OS_WIN
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QLoggingCategory>
#include <QSettings>
#include <QStandardPaths>

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <objbase.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <propkey.h>
#include <propvarutil.h>
#include <wrl/client.h>

Q_LOGGING_CATEGORY(lcIdentity, "wavelane.identity")

namespace {

constexpr wchar_t kAppId[] = L"Wavelane.Client";

//! The picture Windows shows next to the name; it needs a real file.
QString iconFile()
{
    const QString directory = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    QDir().mkpath(directory);
    const QString path = directory + QStringLiteral("/app-icon.png");
    if (!QFile::exists(path)) {
        QFile source(QStringLiteral(":/icons/wavelane-256.png"));
        if (source.open(QIODevice::ReadOnly)) {
            QFile target(path);
            if (target.open(QIODevice::WriteOnly))
                target.write(source.readAll());
        }
    }
    return QDir::toNativeSeparators(path);
}

/*!
    The Start menu entry that ties the name to the program.

    Windows looks a program's label up through the Start menu, where an entry
    carries the id; a program without one shows as "Unknown app" in the media
    panel. Only the installed program (wavelane.exe) keeps the entry, so copies
    made for testing do not take it over.
*/
void ensureStartMenuEntry()
{
    const QString exe = QDir::toNativeSeparators(QCoreApplication::applicationFilePath());
    if (QFileInfo(exe).fileName().compare(QStringLiteral("wavelane.exe"), Qt::CaseInsensitive) != 0
        && !qEnvironmentVariableIsSet("WAVELANE_REGISTER_SHORTCUT"))
        return;

    PWSTR programs = nullptr;
    if (FAILED(SHGetKnownFolderPath(FOLDERID_Programs, 0, nullptr, &programs)))
        return;
    const QString path = QString::fromWCharArray(programs) + QStringLiteral("\\Wavelane.lnk");
    CoTaskMemFree(programs);

    using Microsoft::WRL::ComPtr;
    ComPtr<IShellLinkW> link;
    if (FAILED(CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&link))))
        return;
    ComPtr<IPersistFile> file;
    if (FAILED(link.As(&file)))
        return;

    if (QFile::exists(path) && SUCCEEDED(file->Load(reinterpret_cast<LPCOLESTR>(path.utf16()), STGM_READ))) {
        wchar_t target[MAX_PATH] = {};
        if (SUCCEEDED(link->GetPath(target, MAX_PATH, nullptr, 0))) {
            const QString current = QString::fromWCharArray(target);
            // Already right, or pointing at another copy that still exists: leave it be.
            if (QFileInfo::exists(current))
                return;
        }
    }

    link->SetPath(reinterpret_cast<LPCWSTR>(exe.utf16()));
    link->SetWorkingDirectory(reinterpret_cast<LPCWSTR>(QFileInfo(exe).absolutePath().utf16()));
    link->SetIconLocation(reinterpret_cast<LPCWSTR>(exe.utf16()), 0);
    link->SetDescription(L"Wavelane");

    ComPtr<IPropertyStore> store;
    if (SUCCEEDED(link.As(&store))) {
        PROPVARIANT value;
        if (SUCCEEDED(InitPropVariantFromString(kAppId, &value))) {
            store->SetValue(PKEY_AppUserModel_ID, value);
            store->Commit();
            PropVariantClear(&value);
        }
    }
    if (FAILED(file->Save(reinterpret_cast<LPCOLESTR>(path.utf16()), TRUE)))
        qCWarning(lcIdentity) << "could not create the Start menu entry" << path;
}

} // namespace

namespace AppIdentity {

void registerForShell()
{
    const HRESULT result = SetCurrentProcessExplicitAppUserModelID(kAppId);
    if (FAILED(result))
        qCWarning(lcIdentity) << "could not set the app user model id:" << Qt::hex << result;

    QSettings key(QStringLiteral("HKEY_CURRENT_USER\\Software\\Classes\\AppUserModelId\\")
                      + QString::fromWCharArray(kAppId),
                  QSettings::NativeFormat);
    key.setValue(QStringLiteral("DisplayName"), QStringLiteral("Wavelane"));
    key.setValue(QStringLiteral("IconUri"), iconFile());
    key.setValue(QStringLiteral("IconBackgroundColor"), QStringLiteral("FF0B0C10"));
    key.sync();

    ensureStartMenuEntry();
}

} // namespace AppIdentity

#else

namespace AppIdentity {
void registerForShell() {}
} // namespace AppIdentity

#endif
