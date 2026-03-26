export function createComposerCrossPostController({
    crossPostShell,
    crossPostOptions,
    contentField,
    signal,
    getSelectedFiles,
    getSelectedCitation,
}) {
    const crossPostCopy =
        crossPostShell instanceof HTMLElement
            ? {
                  waitingLabel: crossPostShell.dataset.waitingLabel || "Waiting",
                  readyLabel: crossPostShell.dataset.readyLabel || "Ready",
                  blockedLabel: crossPostShell.dataset.blockedLabel || "Blocked",
                  waitingHint:
                      crossPostShell.dataset.waitingHint ||
                      "Add text, a citation, or media and the available channels will unlock automatically.",
                  reasonDocuments:
                      crossPostShell.dataset.reasonDocuments ||
                      "This channel only supports image and video attachments in the current assistant flow.",
                  reasonMixedMedia:
                      crossPostShell.dataset.reasonMixedMedia ||
                      "This channel needs either images or a single video, not both together.",
                  reasonWechatImageLimit:
                      crossPostShell.dataset.reasonWechatImageLimit ||
                      "WeChat Moments preparation is limited to 9 images here.",
                  reasonSingleVideoOnly:
                      crossPostShell.dataset.reasonSingleVideoOnly ||
                      "This channel can only prepare one video at a time here.",
                  reasonNeedTextOrSupportedMedia:
                      crossPostShell.dataset.reasonNeedTextOrSupportedMedia ||
                      "Add some text, a citation, images, or a single video first.",
                  reasonNeedMedia:
                      crossPostShell.dataset.reasonNeedMedia ||
                      "This channel needs at least one image or video.",
                  reasonInstagramLimit:
                      crossPostShell.dataset.reasonInstagramLimit ||
                      "Instagram preparation is limited to 10 items here.",
                  reasonXiaohongshuImageLimit:
                      crossPostShell.dataset.reasonXiaohongshuImageLimit ||
                      "Xiaohongshu preparation is limited to 9 images here.",
              }
            : null;

    function summarizeCrossPostDraft() {
        const selectedFiles = getSelectedFiles();
        const selectedCitation = getSelectedCitation();
        const imageCount = selectedFiles.filter((entry) => entry.kind === "image").length;
        const videoCount = selectedFiles.filter((entry) => entry.kind === "video").length;
        const documentCount = selectedFiles.filter(
            (entry) => entry.kind !== "image" && entry.kind !== "video",
        ).length;
        const hasCaption = Boolean(contentField?.value.trim()) || Boolean(selectedCitation);

        return {
            imageCount,
            videoCount,
            documentCount,
            mediaCount: imageCount + videoCount,
            hasCaption,
            hasAnyInput: hasCaption || selectedFiles.length > 0,
        };
    }

    function evaluateCrossPostDraft(platform) {
        const summary = summarizeCrossPostDraft();

        if (!crossPostCopy) {
            return {
                state: "waiting",
                hint: "",
            };
        }

        if (!summary.hasAnyInput) {
            return {
                state: "waiting",
                hint: crossPostCopy.waitingHint,
            };
        }

        if (summary.documentCount) {
            return {
                state: "blocked",
                hint: crossPostCopy.reasonDocuments,
            };
        }

        if (platform === "wechat_moments") {
            if (summary.imageCount && summary.videoCount) {
                return {
                    state: "blocked",
                    hint: crossPostCopy.reasonMixedMedia,
                };
            }
            if (summary.imageCount > 9) {
                return {
                    state: "blocked",
                    hint: crossPostCopy.reasonWechatImageLimit,
                };
            }
            if (summary.videoCount > 1) {
                return {
                    state: "blocked",
                    hint: crossPostCopy.reasonSingleVideoOnly,
                };
            }
            if (!summary.mediaCount && !summary.hasCaption) {
                return {
                    state: "blocked",
                    hint: crossPostCopy.reasonNeedTextOrSupportedMedia,
                };
            }
        }

        if (platform === "instagram") {
            if (!summary.mediaCount) {
                return {
                    state: "blocked",
                    hint: crossPostCopy.reasonNeedMedia,
                };
            }
            if (summary.mediaCount > 10) {
                return {
                    state: "blocked",
                    hint: crossPostCopy.reasonInstagramLimit,
                };
            }
        }

        if (platform === "xiaohongshu") {
            if (!summary.mediaCount) {
                return {
                    state: "blocked",
                    hint: crossPostCopy.reasonNeedMedia,
                };
            }
            if (summary.imageCount && summary.videoCount) {
                return {
                    state: "blocked",
                    hint: crossPostCopy.reasonMixedMedia,
                };
            }
            if (summary.imageCount > 9) {
                return {
                    state: "blocked",
                    hint: crossPostCopy.reasonXiaohongshuImageLimit,
                };
            }
            if (summary.videoCount > 1) {
                return {
                    state: "blocked",
                    hint: crossPostCopy.reasonSingleVideoOnly,
                };
            }
        }

        return {
            state: "ready",
            hint: "",
        };
    }

    function render() {
        if (!crossPostOptions.length || !crossPostCopy) {
            return;
        }

        crossPostOptions.forEach((option) => {
            const checkbox = option.querySelector("[data-cross-post-checkbox]");
            const status = option.querySelector("[data-cross-post-status]");
            const hint = option.querySelector("[data-cross-post-hint]");
            const requirement = option.querySelector("[data-cross-post-requirement]");
            const evaluation = evaluateCrossPostDraft(option.dataset.platform || "");

            if (checkbox instanceof HTMLInputElement) {
                checkbox.disabled = evaluation.state !== "ready";
                if (checkbox.disabled) {
                    checkbox.checked = false;
                }
            }

            if (status instanceof HTMLElement) {
                status.textContent =
                    evaluation.state === "ready"
                        ? crossPostCopy.readyLabel
                        : evaluation.state === "blocked"
                          ? crossPostCopy.blockedLabel
                          : crossPostCopy.waitingLabel;
                status.className = `cross-post-status cross-post-status--${evaluation.state}`;
            }

            if (hint instanceof HTMLElement) {
                hint.textContent =
                    evaluation.state === "ready"
                        ? requirement?.textContent || ""
                        : evaluation.hint || crossPostCopy.waitingHint;
            }

            option.classList.toggle("is-ready", evaluation.state === "ready");
            option.classList.toggle("is-disabled", evaluation.state !== "ready");
            option.classList.toggle(
                "is-selected",
                checkbox instanceof HTMLInputElement && checkbox.checked && evaluation.state === "ready",
            );
        });
    }

    crossPostOptions.forEach((option) => {
        const checkbox = option.querySelector("[data-cross-post-checkbox]");
        checkbox?.addEventListener("change", render, { signal });
    });

    contentField?.addEventListener("input", render, { signal });

    return { render };
}
