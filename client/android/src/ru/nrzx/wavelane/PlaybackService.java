package ru.nrzx.wavelane;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.drawable.Icon;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.IBinder;
import android.os.Process;

/**
 * Keeps the music going when the screen is off or the app is in the background, and
 * shows what is playing in the notification shade and on the lock screen.
 *
 * Playback itself stays in the Qt part of the app. This service only holds the process
 * in the foreground (Android would otherwise stop it soon after the screen goes dark),
 * publishes the track in a media session, and passes the buttons (play, pause, next,
 * previous, seek) back to the app through {@link #nativeAction}.
 */
public class PlaybackService extends Service {
    private static final String CHANNEL = "playback";
    private static final int NOTIFICATION_ID = 1;

    private static final String ACTION_PLAY = "ru.nrzx.wavelane.PLAY";
    private static final String ACTION_PAUSE = "ru.nrzx.wavelane.PAUSE";
    private static final String ACTION_NEXT = "ru.nrzx.wavelane.NEXT";
    private static final String ACTION_PREVIOUS = "ru.nrzx.wavelane.PREVIOUS";

    // what the app last reported; the service reads it whenever it has to redraw
    private static String title = "";
    private static String artist = "";
    private static Bitmap cover;
    private static int coverSize = -1;
    private static boolean playing;
    private static long position;
    private static long duration;

    private static PlaybackService instance;
    private MediaSession session;

    /** Codes: 1 play, 2 pause, 3 next, 4 previous, 5 seek to `argument` milliseconds. */
    private static native void nativeAction(int action, long argument);

    /** True while the service is up, i.e. while the music has to keep going in the background. */
    public static boolean isRunning() {
        return instance != null;
    }

    /** Send the app to the background, as the Back button does in a music player. */
    public static void moveToBack(Activity activity) {
        activity.moveTaskToBack(true);
    }

    /** Ask for the permission to show the notification (Android 13 and later). */
    public static void askForNotifications(Activity activity) {
        if (Build.VERSION.SDK_INT >= 33
                && activity.checkSelfPermission("android.permission.POST_NOTIFICATIONS")
                        != PackageManager.PERMISSION_GRANTED) {
            activity.requestPermissions(new String[] {"android.permission.POST_NOTIFICATIONS"}, 1);
        }
    }

    /** Called by the app whenever the track, the play state or the position changes. */
    public static void update(Context context, String newTitle, String newArtist, byte[] coverBytes,
                              boolean hasTrack, boolean isPlaying, long positionMs, long durationMs) {
        if (!hasTrack) {
            context.stopService(new Intent(context, PlaybackService.class));
            return;
        }
        title = newTitle;
        artist = newArtist;
        playing = isPlaying;
        position = positionMs;
        duration = durationMs;

        // decode the picture only when it is a different one
        int size = coverBytes == null ? 0 : coverBytes.length;
        if (size != coverSize) {
            coverSize = size;
            cover = size > 0 ? BitmapFactory.decodeByteArray(coverBytes, 0, size) : null;
        }

        if (instance != null) {
            instance.refresh();
        } else {
            context.startForegroundService(new Intent(context, PlaybackService.class));
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;

        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(
                new NotificationChannel(CHANNEL, "Воспроизведение", NotificationManager.IMPORTANCE_LOW));

        session = new MediaSession(this, "Wavelane");
        session.setCallback(new MediaSession.Callback() {
            @Override public void onPlay() { nativeAction(1, 0); }
            @Override public void onPause() { nativeAction(2, 0); }
            @Override public void onSkipToNext() { nativeAction(3, 0); }
            @Override public void onSkipToPrevious() { nativeAction(4, 0); }
            @Override public void onSeekTo(long positionMs) { nativeAction(5, positionMs); }
        });
        session.setActive(true);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        if (ACTION_PLAY.equals(action)) nativeAction(1, 0);
        else if (ACTION_PAUSE.equals(action)) nativeAction(2, 0);
        else if (ACTION_NEXT.equals(action)) nativeAction(3, 0);
        else if (ACTION_PREVIOUS.equals(action)) nativeAction(4, 0);

        Notification notification = buildNotification();
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
        return START_NOT_STICKY;
    }

    /** Redraw the notification and the media session from the latest state. */
    private void refresh() {
        getSystemService(NotificationManager.class).notify(NOTIFICATION_ID, buildNotification());
    }

    private PendingIntent actionIntent(String action, int code) {
        Intent intent = new Intent(this, PlaybackService.class).setAction(action);
        return PendingIntent.getService(this, code, intent, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private Notification.Action action(int icon, String label, String action, int code) {
        return new Notification.Action.Builder(Icon.createWithResource(this, icon), label, actionIntent(action, code)).build();
    }

    private Notification buildNotification() {
        // what the lock screen and the Bluetooth car kits read
        MediaMetadata.Builder meta = new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, artist)
                .putLong(MediaMetadata.METADATA_KEY_DURATION, duration);
        if (cover != null) {
            meta.putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, cover);
        }
        session.setMetadata(meta.build());
        session.setPlaybackState(new PlaybackState.Builder()
                .setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE
                        | PlaybackState.ACTION_SKIP_TO_NEXT | PlaybackState.ACTION_SEEK_TO)
                .setState(playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED, position, playing ? 1.0f : 0.0f)
                .build());

        Intent open = getPackageManager().getLaunchIntentForPackage(getPackageName());
        PendingIntent openIntent = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder builder = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(getResources().getIdentifier("icon", "drawable", getPackageName()))
                .setContentTitle(title)
                .setContentText(artist)
                .setContentIntent(openIntent)
                .setOngoing(playing)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .addAction(action(android.R.drawable.ic_media_previous, "Назад", ACTION_PREVIOUS, 1))
                .addAction(playing
                        ? action(android.R.drawable.ic_media_pause, "Пауза", ACTION_PAUSE, 2)
                        : action(android.R.drawable.ic_media_play, "Играть", ACTION_PLAY, 3))
                .addAction(action(android.R.drawable.ic_media_next, "Дальше", ACTION_NEXT, 4))
                .setStyle(new Notification.MediaStyle()
                        .setMediaSession(session.getSessionToken())
                        .setShowActionsInCompactView(0, 1, 2));
        if (cover != null) {
            builder.setLargeIcon(cover);
        }
        return builder.build();
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // The app was swiped out of the recent apps: the music ends with it, and the whole
        // process goes, so the next start is a clean one.
        stopSelf();
        Process.killProcess(Process.myPid());
    }

    @Override
    public void onDestroy() {
        if (session != null) {
            session.setActive(false);
            session.release();
        }
        instance = null;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
