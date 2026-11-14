#!/usr/bin/env python3
"""Inventory windows and capture a PNG using Python's standard library and libX11."""
import argparse
import ctypes as c
import ctypes.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import zlib

Window = c.c_ulong


class XImage(c.Structure):
    _fields_ = [("width", c.c_int), ("height", c.c_int),
                ("xoffset", c.c_int), ("format", c.c_int),
                ("data", c.c_void_p), ("byte_order", c.c_int),
                ("bitmap_unit", c.c_int), ("bitmap_bit_order", c.c_int),
                ("bitmap_pad", c.c_int), ("depth", c.c_int),
                ("bytes_per_line", c.c_int), ("bits_per_pixel", c.c_int),
                ("red_mask", c.c_ulong), ("green_mask", c.c_ulong),
                ("blue_mask", c.c_ulong), ("obdata", c.c_void_p)]


def bind(name, args, result):
    function = getattr(x11, name)
    function.argtypes = args
    function.restype = result
    return function


x11 = c.CDLL(ctypes.util.find_library("X11"))
open_display = bind("XOpenDisplay", [c.c_char_p], c.c_void_p)
close_display = bind("XCloseDisplay", [c.c_void_p], c.c_int)
root_window = bind("XDefaultRootWindow", [c.c_void_p], Window)
free_memory = bind("XFree", [c.c_void_p], c.c_int)
query_tree = bind("XQueryTree", [c.c_void_p, Window, c.POINTER(Window),
    c.POINTER(Window), c.POINTER(c.POINTER(Window)), c.POINTER(c.c_uint)], c.c_int)
fetch_name = bind("XFetchName", [c.c_void_p, Window, c.POINTER(c.c_void_p)], c.c_int)
get_geometry = bind("XGetGeometry", [c.c_void_p, Window, c.POINTER(Window),
    c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_uint),
    c.POINTER(c.c_uint), c.POINTER(c.c_uint), c.POINTER(c.c_uint)], c.c_int)
get_image = bind("XGetImage", [c.c_void_p, Window, c.c_int, c.c_int,
    c.c_uint, c.c_uint, c.c_ulong, c.c_int], c.POINTER(XImage))
destroy_image = bind("XDestroyImage", [c.POINTER(XImage)], c.c_int)
sync = bind("XSync", [c.c_void_p, c.c_int], c.c_int)
create_window = bind("XCreateSimpleWindow", [c.c_void_p, Window, c.c_int,
    c.c_int, c.c_uint, c.c_uint, c.c_uint, c.c_ulong, c.c_ulong], Window)
store_name = bind("XStoreName", [c.c_void_p, Window, c.c_char_p], c.c_int)
map_window = bind("XMapWindow", [c.c_void_p, Window], c.c_int)
destroy_window = bind("XDestroyWindow", [c.c_void_p, Window], c.c_int)


class XWindowAttributes(c.Structure):
    _fields_ = [("x", c.c_int), ("y", c.c_int), ("width", c.c_int),
        ("height", c.c_int), ("border_width", c.c_int), ("depth", c.c_int),
        ("visual", c.c_void_p), ("root", Window), ("window_class", c.c_int),
        ("bit_gravity", c.c_int), ("win_gravity", c.c_int), ("backing_store", c.c_int),
        ("backing_planes", c.c_ulong), ("backing_pixel", c.c_ulong),
        ("save_under", c.c_int), ("colormap", c.c_ulong), ("map_installed", c.c_int),
        ("map_state", c.c_int), ("all_event_masks", c.c_long),
        ("your_event_mask", c.c_long), ("do_not_propagate_mask", c.c_long),
        ("override_redirect", c.c_int), ("screen", c.c_void_p)]


class ClientMessageData(c.Union):
    _fields_ = [("b", c.c_char * 20), ("s", c.c_short * 10), ("l", c.c_long * 5)]


class ClientMessage(c.Structure):
    _fields_ = [("type", c.c_int), ("serial", c.c_ulong), ("send_event", c.c_int),
        ("display", c.c_void_p), ("window", Window), ("message_type", c.c_ulong),
        ("format", c.c_int), ("data", ClientMessageData)]


class ButtonEvent(c.Structure):
    _fields_ = [("type", c.c_int), ("serial", c.c_ulong), ("send_event", c.c_int),
        ("display", c.c_void_p), ("window", Window), ("root", Window),
        ("subwindow", Window), ("time", c.c_ulong), ("x", c.c_int), ("y", c.c_int),
        ("x_root", c.c_int), ("y_root", c.c_int), ("state", c.c_uint),
        ("button", c.c_uint), ("same_screen", c.c_int)]


class XEvent(c.Union):
    _fields_ = [("type", c.c_int), ("client", ClientMessage),
                ("button", ButtonEvent), ("pad", c.c_long * 24)]


intern_atom = bind("XInternAtom", [c.c_void_p, c.c_char_p, c.c_int], c.c_ulong)
get_property_raw = bind("XGetWindowProperty", [c.c_void_p, Window, c.c_ulong,
    c.c_long, c.c_long, c.c_int, c.c_ulong, c.POINTER(c.c_ulong),
    c.POINTER(c.c_int), c.POINTER(c.c_ulong), c.POINTER(c.c_ulong),
    c.POINTER(c.c_void_p)], c.c_int)
change_property = bind("XChangeProperty", [c.c_void_p, Window, c.c_ulong,
    c.c_ulong, c.c_int, c.c_int, c.c_void_p, c.c_int], c.c_int)
get_attributes = bind("XGetWindowAttributes", [c.c_void_p, Window,
    c.POINTER(XWindowAttributes)], c.c_int)
send_event = bind("XSendEvent", [c.c_void_p, Window, c.c_int, c.c_long,
    c.POINTER(XEvent)], c.c_int)
pending_events = bind("XPending", [c.c_void_p], c.c_int)
next_event = bind("XNextEvent", [c.c_void_p, c.POINTER(XEvent)], c.c_int)


def property_value(display, window, name):
    actual_type, actual_format = c.c_ulong(), c.c_int()
    count, remaining, pointer = c.c_ulong(), c.c_ulong(), c.c_void_p()
    status = get_property_raw(display, window, intern_atom(display, name.encode(), 0),
        0, 4096, 0, 0, c.byref(actual_type), c.byref(actual_format),
        c.byref(count), c.byref(remaining), c.byref(pointer))
    if status or not pointer:
        return None
    try:
        if actual_format.value == 8:
            return c.string_at(pointer, count.value)
        if actual_format.value == 32:
            values = c.cast(pointer, c.POINTER(c.c_ulong))
            return [int(values[index]) for index in range(count.value)]
        return None
    finally:
        free_memory(pointer)


def window_pid(display, window):
    value = property_value(display, window, "_NET_WM_PID")
    return value[0] if isinstance(value, list) and value else None


def send_close(display, window, expected_pid):
    actual_pid = window_pid(display, window)
    if actual_pid != expected_pid:
        raise ValueError(f"Window PID {actual_pid} does not match owned PID {expected_pid}")
    protocol = intern_atom(display, b"WM_PROTOCOLS", 0)
    delete = intern_atom(display, b"WM_DELETE_WINDOW", 0)
    if delete not in (property_value(display, window, "WM_PROTOCOLS") or []):
        raise RuntimeError("Owned window does not advertise WM_DELETE_WINDOW")
    event = XEvent()
    event.client.type = 33
    event.client.display = display
    event.client.window = window
    event.client.message_type = protocol
    event.client.format = 32
    event.client.data.l[0] = delete
    event.client.data.l[1] = 0
    if not send_event(display, window, 0, 0, c.byref(event)):
        raise RuntimeError("XSendEvent rejected the owned-window close request")
    sync(display, 0)

warp_pointer = bind("XWarpPointer", [c.c_void_p, Window, Window, c.c_int,
    c.c_int, c.c_uint, c.c_uint, c.c_int, c.c_int], c.c_int)
set_focus = bind("XSetInputFocus", [c.c_void_p, Window, c.c_int, c.c_ulong], c.c_int)
translate_coordinates = bind("XTranslateCoordinates", [c.c_void_p, Window, Window,
    c.c_int, c.c_int, c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(Window)], c.c_int)


def send_click(display, window, expected_pid, x, y):
    if window_pid(display, window) != expected_pid:
        raise ValueError("Refusing mouse input to a window owned by another PID")
    bounds = geometry(display, window)
    if not bounds or not (0 <= x < bounds['width'] and 0 <= y < bounds['height']):
        raise ValueError("Refusing a click outside the owned window")
    root = root_window(display)
    root_x, root_y, child = c.c_int(), c.c_int(), Window()
    if not translate_coordinates(display, window, root, x, y,
            c.byref(root_x), c.byref(root_y), c.byref(child)):
        raise RuntimeError("Cannot translate the owned window coordinates")
    set_focus(display, window, 1, 0)
    warp_pointer(display, 0, window, 0, 0, 0, 0, x, y)
    sync(display, 0)
    for kind, state in ((4, 0), (5, 256)):
        event = XEvent()
        event.button.type = kind
        event.button.display = display
        event.button.window = window
        event.button.root = root
        event.button.time = 0
        event.button.x, event.button.y = x, y
        event.button.x_root, event.button.y_root = root_x.value, root_y.value
        event.button.state = state
        event.button.button = 1
        event.button.same_screen = 1
        if not send_event(display, window, 0, 0, c.byref(event)):
            raise RuntimeError("Owned-window mouse event was rejected")
    sync(display, 0)
    return {'window': hex(window), 'pid': expected_pid, 'x': x, 'y': y,
            'root_x': root_x.value, 'root_y': root_y.value}

get_input_focus = bind("XGetInputFocus", [c.c_void_p, c.POINTER(Window),
    c.POINTER(c.c_int)], c.c_int)
query_pointer = bind("XQueryPointer", [c.c_void_p, Window, c.POINTER(Window),
    c.POINTER(Window), c.POINTER(c.c_int), c.POINTER(c.c_int),
    c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_uint)], c.c_int)
resize_window = bind("XResizeWindow", [c.c_void_p, Window, c.c_uint, c.c_uint], c.c_int)


def ancestor_pid(display, window):
    for _depth in range(16):
        if window in (0, 1):
            return None
        pid = window_pid(display, window)
        if pid is not None:
            return pid
        root, parent, children, count = Window(), Window(), c.POINTER(Window)(), c.c_uint()
        if not query_tree(display, window, c.byref(root), c.byref(parent),
                c.byref(children), c.byref(count)):
            return None
        if children:
            free_memory(children)
        if parent.value == window:
            return None
        window = parent.value
    return None


def input_state(display, window, expected_pid):
    actual_pid = window_pid(display, window)
    if actual_pid != expected_pid:
        raise ValueError(f"Window PID {actual_pid} does not match owned PID {expected_pid}")
    focus, revert = Window(), c.c_int()
    get_input_focus(display, c.byref(focus), c.byref(revert))
    root, child = Window(), Window()
    root_x, root_y, local_x, local_y = c.c_int(), c.c_int(), c.c_int(), c.c_int()
    mask = c.c_uint()
    pointer_available = bool(query_pointer(display, window, c.byref(root), c.byref(child),
        c.byref(root_x), c.byref(root_y), c.byref(local_x), c.byref(local_y), c.byref(mask)))
    attributes = XWindowAttributes()
    map_state = attributes.map_state if get_attributes(display, window, c.byref(attributes)) else None
    return {'window': hex(window), 'expected_pid': expected_pid, 'actual_pid': actual_pid,
        'geometry': geometry(display, window), 'map_state': map_state,
        'input_focus': {'window': hex(focus.value), 'revert_to': revert.value,
            'kind': 'None' if focus.value == 0 else 'PointerRoot' if focus.value == 1 else 'Window',
            'ancestor_pid': ancestor_pid(display, focus.value)},
        'pointer': {'available': pointer_available, 'root_x': root_x.value, 'root_y': root_y.value,
            'window_x': local_x.value, 'window_y': local_y.value,
            'child': hex(child.value), 'mask': mask.value}}


def apply_stimulus(display, window, expected_pid, kind):
    before = input_state(display, window, expected_pid)
    details = {}
    if kind == 'focus':
        set_focus(display, window, 1, 0)
        details['operation'] = 'XSetInputFocus to the owned main window; no pointer or size operation'
    elif kind == 'pointer':
        x, y = 17, min(177, before['geometry']['height'] - 2)
        warp_pointer(display, 0, window, 0, 0, 0, 0, x, y)
        details.update(operation='XWarpPointer only; no focus, button or size operation',
                       target_window_x=x, target_window_y=y)
    elif kind == 'resize':
        width = max(64, before['geometry']['width'] - 16)
        height = max(64, before['geometry']['height'] - 16)
        resize_window(display, window, width, height)
        details.update(operation='XResizeWindow only; no focus, pointer or button operation',
                       requested_width=width, requested_height=height)
    elif kind == 'baseline':
        details['operation'] = 'No input or geometry operation'
    else:
        raise ValueError(f'Unsupported isolated stimulus: {kind}')
    sync(display, 0)
    after = input_state(display, window, expected_pid)
    return {'kind': kind, 'before': before, 'after_server_sync': after, 'details': details,
        'focus_window_changed': before['input_focus']['window'] != after['input_focus']['window'],
        'pointer_position_changed': (before['pointer']['root_x'], before['pointer']['root_y']) !=
            (after['pointer']['root_x'], after['pointer']['root_y']),
        'geometry_changed': before['geometry'] != after['geometry']}

def geometry(display, window):
    root, x, y = Window(), c.c_int(), c.c_int()
    width, height, border, depth = [c.c_uint() for _ in range(4)]
    if not get_geometry(display, window, c.byref(root), c.byref(x), c.byref(y),
            c.byref(width), c.byref(height), c.byref(border), c.byref(depth)):
        return None
    return dict(x=x.value, y=y.value, width=width.value, height=height.value,
                border=border.value, depth=depth.value)


def window_inventory(display, parent, depth=0):
    if depth > 12:
        return []
    root, ancestor, children, count = Window(), Window(), c.POINTER(Window)(), c.c_uint()
    if not query_tree(display, parent, c.byref(root), c.byref(ancestor),
            c.byref(children), c.byref(count)):
        return []
    identifiers = [children[index] for index in range(min(count.value, 4096))]
    if children:
        free_memory(children)
    result = []
    for identifier in identifiers:
        name_pointer = c.c_void_p()
        name = ""
        if fetch_name(display, identifier, c.byref(name_pointer)) and name_pointer:
            name = c.string_at(name_pointer).decode("utf-8", "replace")
            free_memory(name_pointer)
        utf8_name = property_value(display, identifier, "_NET_WM_NAME")
        if isinstance(utf8_name, bytes):
            name = utf8_name.decode("utf-8", "replace")
        attributes = XWindowAttributes()
        mapped = None
        if get_attributes(display, identifier, c.byref(attributes)):
            mapped = attributes.map_state
        wm_class = property_value(display, identifier, "WM_CLASS")
        classes = wm_class.rstrip(b"\0").decode("utf-8", "replace").split("\0") \
            if isinstance(wm_class, bytes) else []
        result.append(dict(window=hex(identifier), parent=hex(parent),
                           name=name, pid=window_pid(display, identifier),
                           map_state=mapped, wm_class=classes,
                           geometry=geometry(display, identifier)))
        result.extend(window_inventory(display, identifier, depth + 1))
    return result


def png_chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + \
        struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)


def capture(display, root, output):
    size = geometry(display, root)
    width, height = size["width"], size["height"]
    handle = get_image(display, root, 0, 0, width, height, c.c_ulong(-1).value, 2)
    if not handle:
        raise RuntimeError("XGetImage failed")
    try:
        info = handle.contents
        if info.bits_per_pixel not in (24, 32) or \
                (info.red_mask, info.green_mask, info.blue_mask) != (0xff0000, 0xff00, 0xff):
            raise RuntimeError("Unsupported XImage pixel format")
        data = c.string_at(info.data, info.bytes_per_line * height)
        stride, pixel_bytes = info.bytes_per_line, info.bits_per_pixel // 8
        order = "little" if info.byte_order == 0 else "big"
        raw = bytearray()
        sample = None
        for y in range(height):
            raw.append(0)
            for x in range(width):
                offset = y * stride + x * pixel_bytes
                pixel = int.from_bytes(data[offset:offset + pixel_bytes], order)
                rgb = (pixel >> 16 & 255, pixel >> 8 & 255, pixel & 255)
                if (x, y) == (25, 35):
                    sample = rgb
                raw.extend(rgb)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"\x89PNG\r\n\x1a\n" +
            png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            png_chunk(b"IDAT", zlib.compress(raw, 6)) + png_chunk(b"IEND", b""))
        return dict(path=str(output), width=width, height=height,
                    depth=info.depth, bits_per_pixel=info.bits_per_pixel,
                    sample_rgb=sample)
    finally:
        destroy_image(handle)

