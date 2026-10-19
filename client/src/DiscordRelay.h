#pragma once

#include <QString>

/*!
 * The small helper process that holds the connection to Discord.
 *
 * Discord forgets a presence when the connection that set it asks it to, and
 * when that connection closes — but a program that is killed from the task
 * manager can do neither, and Discord can go on showing "Listening to Wavelane"
 * for a long while. So the connection is kept by a second, tiny process, started
 * by the client and not part of its process tree. It takes the activity from the
 * client over a local socket, and the moment that socket closes for any reason
 * (the window was closed, Alt+F4, the process was killed) it clears the presence
 * itself and exits.
 *
 * It is the same executable, started as `wavelane --discord-relay ...`; it never
 * creates a window.
 */
namespace DiscordRelay {

//! The command-line switch that makes the executable run as the helper.
inline const char *kSwitch = "--discord-relay";

//! True when `argv` asks for the helper.
bool requested(int argc, char *argv[]);

//! Run the helper to completion and return the process exit code.
int run(int argc, char *argv[]);

//! Name of the local socket the client listens on for the helper.
QString controlName(qint64 clientPid);

} // namespace DiscordRelay
