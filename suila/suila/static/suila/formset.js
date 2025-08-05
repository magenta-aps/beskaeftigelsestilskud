/*
SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
SPDX-License-Identifier: MPL-2.0
*/
/* eslint-env jquery */
/* global $ */
$(function(){
    $.fn.extend({
        'formset': function(name, formPrototypeContainer, autoAdd) {
            const formContainer = this;
            const management = {
                total: formContainer.siblings('input[name="' + name + '-TOTAL_FORMS"]'),
                initial: formContainer.siblings('input[name="' + name + '-INITIAL_FORMS"]'),
                min: formContainer.siblings('input[name="' + name + '-MIN_NUM_FORMS"]'),
                max: formContainer.siblings('input[name="' + name + '-MAX_NUM_FORMS"]')
            };
            const formPrototype = formPrototypeContainer.children().first();

            const updateTotal = function () {
                management.total.val(formContainer.children().length);
            };

            const addForm = function (update) {
                const form = formPrototype.clone();
                const nextId = parseInt(management.total.val());
                form.find('*').each(function () {
                    for (let i = 0; i < this.attributes.length; i++) {
                        this.attributes[i].nodeValue = this.attributes[i].nodeValue.replace('__prefix__', nextId);
                    }
                });
                formContainer.trigger("subform.pre_add", form);
                formContainer.append(form);
                formContainer.trigger("subform.post_add", form);
                if (update !== false) {
                    updateTotal();
                }
                return form;
            };

            const removeForm = function (form, update) {
                if (form.parent().first().is(formContainer)) {
                    const parent = form.parent();
                    form.trigger("subform.pre_remove");
                    form.remove();
                    if (update !== false) {
                        updateTotal();
                    }
                    parent.trigger("subform.post_remove", form);
                }
            };

            if (autoAdd) {
                const updateForm = function () {
                    const rows = formContainer.find(".row");
                    let emptyRows = 0;
                    rows.each((index, element) => {
                        let empty = true;
                        $(element).find("input,select,textarea").each((index, element) => {
                            if (element.value !== "") {
                                empty = false;
                                return true;
                            }
                        });
                        if (empty) {
                            emptyRows++;
                        }
                    });
                    if (emptyRows === 0) {
                        addForm(true);
                    }
                };
                formContainer.on("change", "input,select,textarea", updateForm);
                updateForm();
            }

            return {
                'addForm': addForm,
                'removeForm': removeForm
            };
        }
    });
});

function initFormset(formsetContainerId, formsetPrototypeId) {
    const container = $("#" + formsetContainerId);
    const prototype = $("#" + formsetPrototypeId);

    const formset = container.formset("attachments", prototype, true);

    const subformAdded = function (subform) {
        if (!(subform instanceof $)) {
            subform = $(subform);
        }
        subform.find(".remove-row").click(removeForm.bind(subform, subform));
        subformsUpdated();
    };

    const subformRemoved = function () {
        const rows = container.find(".row");
        rows.each(function (index) {
            $(this).find("input[name],select[name]").each(function () {
                this.id = this.id.replace(/-\d+-/, "-" + index + "-");
                this.name = this.name.replace(/-\d+-/, "-" + index + "-");
            });
        });
        subformsUpdated();
    };

    const subformsUpdated = function () {
        const rows = container.find(".row");
        const lastRow = rows.last();
        rows.find(".remove-row").show();
        lastRow.find(".remove-row").hide();
    };

    const removeForm = function (subform) {
        subform.slideUp(400, () => {
            formset.removeForm(subform, true);
        });
    };

    container.find(".row").each(function () {
        subformAdded(this);
    });

    container.on("subform.post_add", function (event, row) {
        subformAdded(row);
        $(row).slideDown(400);
    });

    container.on("subform.pre_add", function (event, row) {
        $(row).hide();
    });

    container.on("subform.post_remove", function (event, row) {
        subformRemoved(row);
    });
}