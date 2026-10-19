package ru.nrzx.wavelane;

import android.content.Intent;
import android.os.Process;

import org.qtproject.qt.android.bindings.QtActivity;

/**
 * The app's window. It is Qt's activity with one addition: when the window is really
 * closed (not just sent to the background), the whole process goes with it.
 *
 * Without that, the playback service keeps the process alive after the window is gone,
 * the music carries on, and starting the app again finds a Qt that has already shut down
 * its window and shows nothing.
 */
public class WavelaneActivity extends QtActivity {
    @Override
    protected void onDestroy() {
        final boolean closing = isFinishing();
        super.onDestroy();
        if (closing) {
            stopService(new Intent(this, PlaybackService.class));
            Process.killProcess(Process.myPid());
        }
    }
}
