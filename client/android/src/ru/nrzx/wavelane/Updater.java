package ru.nrzx.wavelane;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.core.content.FileProvider;

import java.io.File;

/**
 * Hands a downloaded update to the system installer. The file has to lie in the app's files
 * directory, which is what the file provider that Qt declares in the manifest serves.
 */
public final class Updater {
    private Updater() {}

    /**
     * @return true when the installer was opened; false when the person first has to allow this
     *         app to install packages (the settings page for it is opened instead).
     */
    public static boolean install(Context context, String path) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                && !context.getPackageManager().canRequestPackageInstalls()) {
            Intent settings = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + context.getPackageName()));
            settings.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(settings);
            return false;
        }

        Uri uri = FileProvider.getUriForFile(context, context.getPackageName() + ".qtprovider", new File(path));
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, "application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(intent);
        return true;
    }
}
