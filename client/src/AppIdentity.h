#pragma once

/*!
 * Tells Windows what this program is called.
 *
 * The media panel, the taskbar and notifications label a program by its "app
 * user model id" and look the display name up under that id. A program that has
 * not registered one is shown as "Unknown app".
 */
namespace AppIdentity {

//! Name this process and register its display name and icon. Call once, early.
void registerForShell();

} // namespace AppIdentity
