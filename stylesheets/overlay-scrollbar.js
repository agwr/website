// Replace the native document scrollbar with a floating overlay scrollbar so
// long pages don't reserve gutter width and shift the centered content. Styled
// via the `os-theme-native` theme in styles.css to look like the macOS bar.
(function () {
  if (typeof OverlayScrollbarsGlobal === "undefined") return;
  OverlayScrollbarsGlobal.OverlayScrollbars(document.body, {
    scrollbars: {
      theme: "os-theme-native",
      autoHide: "move",
      autoHideDelay: 1300,
      clickScroll: true,
    },
    // Always use the overlay, even where the OS already paints overlay
    // scrollbars, so layout is identical across platforms.
    cancel: { nativeScrollbarsOverlaid: false },
  });
})();
