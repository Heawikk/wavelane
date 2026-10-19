package ru.nrzx.wavelane;

import android.content.Intent;
import android.os.Process;

import org.qtproject.qt.android.bindings.QtActivity;

/**
 * The app's window. It is Qt's activity with one addition: when the window is really
 * gone (closed, swiped out of the recent apps, or destroyed by the system), the whole
 * process goes with it.
 *
 * Without that, the playback service keeps the process alive after the window is gone,
 * the music carries on, and starting the app again finds a Qt that has already shut down
 * its window and shows nothing.
 *
 * The process has to be ended before Qt's own teardown, not after it: Qt's onDestroy waits
 * for its thread to finish, and with the main loop replaced for background playback (see
 * main.cpp) that thread never finishes, so the main thread hangs there with the music still
 * playing and nothing, not even the notification buttons, able to reach it.
 */
public class WavelaneActivity extends QtActivity {
    @Override
    protected void onDestroy() {
        // A rotation or similar recreates the window in the same process; that must survive.
        if (!isChangingConfigurations()) {
            stopService(new Intent(this, PlaybackService.class));
            Process.killProcess(Process.myPid());
        }
        super.onDestroy();
    }
}
