$(function() {
    const fileInputContainer = $(".file-input");
    fileInputContainer.on("dragenter", function () {
        $(this).addClass("dragover");
    });
    fileInputContainer.on("dragover", function (event) {
        event.preventDefault();
        $(this).addClass("dragover");
    });
    fileInputContainer.on("dragleave", function () {
        $(this).removeClass("dragover");
    });
    fileInputContainer.on("drop", function (event) {
        event.preventDefault();
        $(this).removeClass("dragover");
        const fileInput = $(this).find("input[type=file]");
        const accept = fileInput.attr("accept");
        const acceptList = accept && accept.split(",");
        const dataTransfer = new DataTransfer();

        for (const item of event.originalEvent.dataTransfer.items) {
            if (item.kind === "file") {
                const file = item.getAsFile();
                if (acceptList) {
                    const extension = file.name.includes(".") ? file.name.substring(file.name.lastIndexOf(".")) : null;
                    if (!(acceptList.includes(file.type) || (extension && acceptList.includes(extension)))) {
                        continue;
                    }
                }
                dataTransfer.items.add(file);
                break;
            }
        }

        fileInput.get(0).files = dataTransfer.files;
        fileInput.trigger("change");
    });
});
