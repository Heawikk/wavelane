// The Windows headers come first and on purpose: C++/WinRT and Qt both define
// names the other would trip over, and including WinRT before any Qt header
// keeps Qt's `signals`/`emit` macros out of it.
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Media.h>
#include <winrt/Windows.Storage.Streams.h>

#include <systemmediatransportcontrolsinterop.h>
#endif

#include "MediaSession.h"

#include "ApiClient.h"
#include "Player.h"

#include <QLoggingCategory>
#include <QPointer>
#include <QTimer>
#include <QWindow>

#include <atomic>
#include <mutex>
#include <thread>

Q_LOGGING_CATEGORY(lcMedia, "wavelane.media")

#ifdef _WIN32

namespace wm = winrt::Windows::Media;
namespace wf = winrt::Windows::Foundation;
namespace ws = winrt::Windows::Storage::Streams;

struct MediaSession::Impl
{
    wm::SystemMediaTransportControls controls{nullptr};
    winrt::event_token buttonToken{};
    winrt::event_token seekToken{};
    //! Bumped for every metadata push, so a slow one cannot overwrite a newer one.
    std::atomic<int> generation{0};
    //! Updates are built on separate threads; the display updater is one object.
    std::mutex updateLock;
};

namespace {

winrt::hstring toHString(const QString &text)
{
    return winrt::hstring(reinterpret_cast<const wchar_t *>(text.utf16()),
                          static_cast<uint32_t>(text.size()));
}

wf::TimeSpan fromMilliseconds(qint64 milliseconds)
{
    return wf::TimeSpan{std::chrono::milliseconds(milliseconds)};
}

} // namespace

#else
struct MediaSession::Impl
{
};
#endif

MediaSession::MediaSession(Player *player, ApiClient *api, QObject *parent)
    : QObject(parent)
    , m_impl(std::make_unique<Impl>())
    , m_player(player)
    , m_api(api)
    , m_timelineTimer(new QTimer(this))
{
    connect(m_player, &Player::currentTrackChanged, this, &MediaSession::syncTrack);
    connect(m_player, &Player::playingChanged, this, [this]() {
        syncState();
        syncTimeline();
    });
    connect(m_player, &Player::bufferingChanged, this, &MediaSession::syncState);
    connect(m_player, &Player::durationChanged, this, &MediaSession::syncTimeline);
    connect(m_player, &Player::seeked, this, &MediaSession::syncTimeline);

    // Windows extrapolates the position while playing; a periodic correction
    // keeps it from drifting over a long track.
    m_timelineTimer->setInterval(5000);
    connect(m_timelineTimer, &QTimer::timeout, this, &MediaSession::syncTimeline);
}

MediaSession::~MediaSession()
{
#ifdef _WIN32
    if (m_impl && m_impl->controls) {
        try {
            m_impl->controls.ButtonPressed(m_impl->buttonToken);
            m_impl->controls.PlaybackPositionChangeRequested(m_impl->seekToken);
            m_impl->controls.IsEnabled(false);
        } catch (...) {
        }
    }
#endif
}

void MediaSession::attach(QWindow *window)
{
#ifdef _WIN32
    if (!window || m_impl->controls)
        return;

    try {
        const HWND hwnd = reinterpret_cast<HWND>(window->winId());
        auto interop = winrt::get_activation_factory<wm::SystemMediaTransportControls,
                                                     ISystemMediaTransportControlsInterop>();
        winrt::check_hresult(interop->GetForWindow(
            hwnd, winrt::guid_of<wm::ISystemMediaTransportControls>(),
            winrt::put_abi(m_impl->controls)));

        auto &controls = m_impl->controls;
        controls.IsEnabled(true);
        controls.IsPlayEnabled(true);
        controls.IsPauseEnabled(true);
        controls.IsNextEnabled(true);
        // The wave has no "previous", and neither do lists we walk forward.
        controls.IsPreviousEnabled(false);
        controls.IsStopEnabled(false);

        // Both handlers run on a thread of Windows' choosing, so they only
        // post a message back to the Qt thread and never touch the player.
        QPointer<MediaSession> self(this);
        m_impl->buttonToken = controls.ButtonPressed(
            [self](wm::SystemMediaTransportControls const &,
                   wm::SystemMediaTransportControlsButtonPressedEventArgs const &args) {
                const auto button = args.Button();
                QMetaObject::invokeMethod(
                    self.data(),
                    [self, button]() {
                        if (!self)
                            return;
                        switch (button) {
                        case wm::SystemMediaTransportControlsButton::Play:
                            emit self->playRequested();
                            break;
                        case wm::SystemMediaTransportControlsButton::Pause:
                            emit self->pauseRequested();
                            break;
                        case wm::SystemMediaTransportControlsButton::Next:
                            emit self->nextRequested();
                            break;
                        case wm::SystemMediaTransportControlsButton::Previous:
                            emit self->previousRequested();
                            break;
                        default:
                            break;
                        }
                    },
                    Qt::QueuedConnection);
            });
        m_impl->seekToken = controls.PlaybackPositionChangeRequested(
            [self](wm::SystemMediaTransportControls const &,
                   wm::PlaybackPositionChangeRequestedEventArgs const &args) {
                const qint64 positionMs = std::chrono::duration_cast<std::chrono::milliseconds>(
                                              args.RequestedPlaybackPosition())
                                              .count();
                QMetaObject::invokeMethod(
                    self.data(),
                    [self, positionMs]() {
                        if (self)
                            emit self->seekRequested(positionMs);
                    },
                    Qt::QueuedConnection);
            });

        m_active = true;
        emit activeChanged();
        qCInfo(lcMedia) << "system media controls attached";
        syncTrack();
    } catch (const winrt::hresult_error &error) {
        qCWarning(lcMedia) << "could not attach system media controls:"
                           << QString::fromWCharArray(error.message().c_str());
        m_impl->controls = nullptr;
    }
#else
    Q_UNUSED(window)
#endif
}

void MediaSession::syncTrack()
{
    if (!m_active)
        return;

    const QVariantMap track = m_player->currentTrack();
    const QString id = track.value(QStringLiteral("id")).toString();
    const QString cover = track.value(QStringLiteral("coverPath")).toString();

    if (id != m_trackId) {
        m_trackId = id;
        // A different track: its cover is not the previous one's.
        if (cover != m_coverPath)
            m_cover.clear();
        m_coverPath = cover;

        pushMetadata(false);

        // The text is up straight away; the picture follows once it has arrived.
        if (!cover.isEmpty() && m_cover.isEmpty()) {
            const QString wantedId = id;
            m_api->fetchBytes(m_api->coverUrl(cover), [this, wantedId](const QByteArray &bytes) {
                if (bytes.isEmpty() || wantedId != m_trackId)
                    return;
                m_cover = bytes;
                pushMetadata(true);
            });
        } else if (!m_cover.isEmpty()) {
            pushMetadata(true);
        }
    } else {
        // Same track, but its like flag or similar changed: nothing to resend.
    }

    syncState();
    syncTimeline();
}

void MediaSession::pushMetadata(bool withCover)
{
#ifdef _WIN32
    if (!m_active || !m_impl->controls)
        return;

    const QVariantMap track = m_player->currentTrack();
    const bool hasTrack = !track.value(QStringLiteral("id")).toString().isEmpty();

    const QString title = track.value(QStringLiteral("title")).toString();
    const QString artist = track.value(QStringLiteral("artistName")).toString();
    const QString album = track.value(QStringLiteral("albumTitle")).toString();
    const QByteArray cover = withCover ? m_cover : QByteArray();
    const int generation = ++m_impl->generation;
    auto controls = m_impl->controls;
    Impl *impl = m_impl.get();

    // Building the thumbnail waits on asynchronous Windows calls, which must
    // not block the thread that runs the UI, so the whole update runs on its
    // own short-lived thread. The controls object is safe to use from there.
    std::thread([=]() {
        try {
            winrt::init_apartment(winrt::apartment_type::multi_threaded);
            std::lock_guard lock(impl->updateLock);
            // A newer update was queued behind this one: skip the stale work.
            if (generation != impl->generation.load())
                return;

            auto updater = controls.DisplayUpdater();
            if (!hasTrack) {
                updater.ClearAll();
                updater.Update();
                return;
            }

            updater.ClearAll();
            updater.Type(wm::MediaPlaybackType::Music);
            auto music = updater.MusicProperties();
            music.Title(toHString(title));
            music.Artist(toHString(artist));
            music.AlbumTitle(toHString(album));

            if (!cover.isEmpty()) {
                ws::InMemoryRandomAccessStream stream;
                ws::DataWriter writer(stream);
                const auto *begin = reinterpret_cast<const uint8_t *>(cover.constData());
                writer.WriteBytes(winrt::array_view<const uint8_t>(begin, begin + cover.size()));
                writer.StoreAsync().get();
                writer.DetachStream();
                stream.Seek(0);
                updater.Thumbnail(ws::RandomAccessStreamReference::CreateFromStream(stream));
                qCDebug(lcMedia) << "thumbnail" << cover.size() << "bytes";
            }

            // Another update was started while this one was being built.
            if (generation != impl->generation.load())
                return;
            updater.Update();
        } catch (const winrt::hresult_error &error) {
            qCWarning(lcMedia) << "could not update the media display:"
                               << QString::fromWCharArray(error.message().c_str());
        }
    }).detach();
#else
    Q_UNUSED(withCover)
#endif
}

void MediaSession::syncState()
{
#ifdef _WIN32
    if (!m_active || !m_impl->controls)
        return;
    try {
        auto &controls = m_impl->controls;
        const bool hasTrack = m_player->hasTrack();
        wm::MediaPlaybackStatus status = wm::MediaPlaybackStatus::Stopped;
        if (hasTrack) {
            if (m_player->playing())
                status = m_player->buffering() ? wm::MediaPlaybackStatus::Changing
                                               : wm::MediaPlaybackStatus::Playing;
            else
                status = wm::MediaPlaybackStatus::Paused;
        }
        controls.PlaybackStatus(status);
        controls.IsNextEnabled(hasTrack);

        if (hasTrack && m_player->playing())
            m_timelineTimer->start();
        else
            m_timelineTimer->stop();
    } catch (const winrt::hresult_error &error) {
        qCWarning(lcMedia) << "state update failed:"
                           << QString::fromWCharArray(error.message().c_str());
    }
#endif
}

void MediaSession::syncTimeline()
{
#ifdef _WIN32
    if (!m_active || !m_impl->controls || !m_player->hasTrack())
        return;
    try {
        const qint64 duration = m_player->duration();
        if (duration <= 0)
            return;
        wm::SystemMediaTransportControlsTimelineProperties timeline;
        timeline.StartTime(fromMilliseconds(0));
        timeline.MinSeekTime(fromMilliseconds(0));
        timeline.EndTime(fromMilliseconds(duration));
        timeline.MaxSeekTime(fromMilliseconds(duration));
        timeline.Position(fromMilliseconds(qBound<qint64>(0, m_player->position(), duration)));
        m_impl->controls.UpdateTimelineProperties(timeline);
    } catch (const winrt::hresult_error &error) {
        qCWarning(lcMedia) << "timeline update failed:"
                           << QString::fromWCharArray(error.message().c_str());
    }
#endif
}
