(dialog) => {
  const visible = (element) => !!(element && element.getClientRects().length);
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();
  const nearbyValidationMessage = (element) => {
    const wrapper = element.closest("fieldset, .fb-dash-form-element, .jobs-easy-apply-form-section__grouping, .artdeco-text-input--container, .artdeco-inline-feedback, .artdeco-form__group");
    if (!wrapper) return null;
    const candidates = Array.from(
      wrapper.querySelectorAll("[role='alert'], [aria-live='assertive'], [aria-live='polite'], .artdeco-inline-feedback__message, .fb-dash-form-element__error-message, .artdeco-input-helper-text")
    )
      .filter((node) => node !== element && visible(node))
      .map((node) => clean(node.textContent))
      .filter(Boolean);
    return candidates[0] || null;
  };

  const promptCandidates = (element) => {
    const id = element.getAttribute("id");
    const wrapper = element.closest("fieldset, .fb-dash-form-element, .jobs-easy-apply-form-section__grouping, .artdeco-text-input--container");
    const forLabel = id ? dialog.querySelector(`label[for="${id}"]`) : null;
    const closestLabel = element.closest("label");
    const nodes = [
      element.getAttribute("aria-label"),
      forLabel && forLabel.textContent,
      closestLabel && closestLabel.textContent,
      wrapper && wrapper.querySelector("legend") && wrapper.querySelector("legend").textContent,
      wrapper && wrapper.querySelector(".fb-dash-form-element__label") && wrapper.querySelector(".fb-dash-form-element__label").textContent,
      wrapper && wrapper.querySelector("h3, h4, p, span") && wrapper.querySelector("h3, h4, p, span").textContent,
      element.getAttribute("placeholder"),
      element.getAttribute("name"),
    ];
    return nodes.map((item) => clean(item)).filter(Boolean);
  };

  const titleEl = dialog.querySelector("h2, h3");
  const stepTitle = clean(titleEl && titleEl.textContent);
  const progressMatch = clean(dialog.innerText).match(/(\d+)%/);
  const progressPercent = progressMatch ? Number(progressMatch[1]) : null;

  const visibleButtons = Array.from(dialog.querySelectorAll("button"))
    .filter(visible)
    .map((button) => clean(button.textContent))
    .filter(Boolean);
  const primaryActionLabel = visibleButtons.length ? visibleButtons[visibleButtons.length - 1] : null;
  const secondaryActionLabels = visibleButtons.slice(0, -1);

  const sectionTitles = Array.from(dialog.querySelectorAll("h3, h4"))
    .filter(visible)
    .map((node) => clean(node.textContent))
    .filter((text) => text && text !== stepTitle);

  const rawElements = [];
  const seenElements = new Set();

  const controls = Array.from(dialog.querySelectorAll("input, select, textarea")).filter(visible);
  const documentChoiceInputs = controls.filter((element) => {
    const rawType = (element.getAttribute("type") || "").toLowerCase();
    if (rawType !== "radio") return false;
    const card = element.closest("label, div");
    const text = clean(card && card.textContent);
    return text.includes(".pdf") || text.includes(".doc") || text.includes(".docx");
  });

  if (documentChoiceInputs.length) {
    const options = documentChoiceInputs
      .map((element) => {
        const card = element.closest("label, div");
        const text = clean(card && card.textContent);
        const fileMatch = text.match(/([^\n]+?\.(?:pdf|docx?|PDF|DOCX?))/);
        return fileMatch ? clean(fileMatch[1]) : text;
      })
      .filter(Boolean);
    const selected = documentChoiceInputs.find((element) => element.checked);
    const selectedText = selected
      ? (() => {
          const card = selected.closest("label, div");
          const text = clean(card && card.textContent);
          const fileMatch = text.match(/([^\n]+?\.(?:pdf|docx?|PDF|DOCX?))/);
          return fileMatch ? clean(fileMatch[1]) : text;
        })()
      : null;
    rawElements.push({
      element_id: "document_choice_resume",
      label: "Resume",
      control_type: "document_choice",
      required: true,
      current_value: selectedText,
      options,
      options_count: options.length,
      suggestions: [],
      field_name: null,
      field_id: null,
      html_type: "radio",
      input_mode: null,
      pattern: null,
      placeholder: null,
      validation_message: null,
      min_value: null,
      max_value: null,
    });
  }

  const processedRadioNames = new Set();
  for (const element of controls) {
    const tagName = element.tagName.toLowerCase();
    const rawType = (element.getAttribute("type") || tagName).toLowerCase();
    if (rawType === "hidden" || rawType === "file") continue;
    if (documentChoiceInputs.includes(element)) continue;

    if (rawType === "radio") {
      const name = element.getAttribute("name") || element.getAttribute("id") || "radio";
      if (processedRadioNames.has(name)) continue;
      processedRadioNames.add(name);
      const group = controls.filter((candidate) => {
        const candidateType = (candidate.getAttribute("type") || "").toLowerCase();
        return candidateType === "radio"
          && (candidate.getAttribute("name") || candidate.getAttribute("id") || "radio") === name
          && !documentChoiceInputs.includes(candidate);
      });
      const options = group.map((candidate) => {
        const id = candidate.getAttribute("id");
        const label = id ? dialog.querySelector(`label[for="${id}"]`) : candidate.closest("label");
        return clean((label && label.textContent) || candidate.getAttribute("value") || "");
      }).filter(Boolean);

      const wrapper = element.closest("fieldset, .fb-dash-form-element, .jobs-easy-apply-form-section__grouping");
      const promptTexts = [];
      if (wrapper) {
        const labels = Array.from(wrapper.querySelectorAll("legend, .fb-dash-form-element__label, h3, h4, p, span, div"))
          .filter(visible)
          .map((node) => clean(node.textContent))
          .filter(Boolean);
        for (const text of labels) {
          if (options.includes(text)) continue;
          if (options.some((option) => text === `${option} Required`)) continue;
          if (text.length <= 3) continue;
          promptTexts.push(text);
        }
      }
      const promptText = clean(promptTexts[0] || promptCandidates(element)[0] || "");
      if (!promptText) continue;

      const checked = group.find((candidate) => candidate.checked);
      const checkedLabel = checked
        ? (() => {
            const id = checked.getAttribute("id");
            const label = id ? dialog.querySelector(`label[for="${id}"]`) : checked.closest("label");
            return clean((label && label.textContent) || checked.getAttribute("value") || "");
          })()
        : null;

      const keyBase = name.replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "") || "radio";
      if (!seenElements.has(keyBase)) {
        seenElements.add(keyBase);
        rawElements.push({
          element_id: keyBase,
          label: promptText,
          control_type: "radio_group",
          required: true,
          current_value: checkedLabel,
          options,
          options_count: options.length,
          suggestions: [],
          field_name: name,
          field_id: element.getAttribute("id"),
          html_type: "radio",
          input_mode: null,
          pattern: null,
          placeholder: null,
          validation_message: null,
          min_value: null,
          max_value: null,
        });
      }
      continue;
    }

    const prompts = promptCandidates(element);
    const promptText = clean(prompts[0] || "");
    if (!promptText) continue;

    let inputType = rawType;
    let currentValue = element.value || null;
    let options = [];
    let suggestions = [];
    if (tagName === "select") {
      inputType = "select";
      options = Array.from(element.options).map((option) => clean(option.textContent)).filter(Boolean);
      currentValue = element.selectedOptions[0] ? clean(element.selectedOptions[0].textContent) : null;
    } else if (tagName === "textarea") {
      inputType = "textarea";
    } else if (element.getAttribute("role") === "combobox" || element.getAttribute("aria-autocomplete") === "list") {
      inputType = "typeahead";
      suggestions = Array.from(dialog.querySelectorAll("[role='option']"))
        .filter(visible)
        .map((option) => clean(option.textContent))
        .filter(Boolean)
        .slice(0, 8);
    } else if (rawType === "checkbox") {
      inputType = "checkbox";
      currentValue = element.checked ? "Yes" : "No";
    } else if (!["email", "tel", "url", "text"].includes(rawType)) {
      inputType = "text";
    }

    const keyBase = (element.getAttribute("name") || element.getAttribute("id") || promptText.toLowerCase())
      .replace(/[^a-z0-9]+/gi, "_")
      .replace(/^_+|_+$/g, "") || "question";
    if (!seenElements.has(keyBase)) {
      seenElements.add(keyBase);
      rawElements.push({
        element_id: keyBase,
        label: promptText,
        control_type: inputType,
        required: element.required || element.getAttribute("aria-required") === "true" || promptText.includes("*"),
        current_value: currentValue,
        options,
        options_count: options.length,
        suggestions,
        field_name: element.getAttribute("name"),
        field_id: element.getAttribute("id"),
        html_type: rawType,
        input_mode: element.getAttribute("inputmode"),
        pattern: element.getAttribute("pattern"),
        placeholder: element.getAttribute("placeholder"),
        validation_message: element.validationMessage || nearbyValidationMessage(element) || null,
        min_value: element.getAttribute("min"),
        max_value: element.getAttribute("max"),
      });
    }
  }

  const rawRecordLists = [];
  for (const sectionTitle of sectionTitles) {
    const normalized = sectionTitle.toLowerCase();
    if (!normalized.includes("expérience") && !normalized.includes("formation") && !normalized.includes("experience") && !normalized.includes("education")) {
      continue;
    }
    const itemPreviewMatches = Array.from(dialog.querySelectorAll("div"))
      .filter(visible)
      .map((node) => clean(node.textContent))
      .filter((text) => (text.includes("Edit") || text.includes("Remove")) && text.length <= 160);
    const deduped = [...new Set(itemPreviewMatches)].filter(Boolean).slice(0, 8);
    if (!deduped.length) continue;
    rawRecordLists.push({
      section_title: sectionTitle,
      item_previews: deduped,
      item_count: deduped.length,
    });
  }

  return {
    step_title: stepTitle || null,
    progress_percent: progressPercent,
    section_titles: sectionTitles,
    primary_action_label: primaryActionLabel,
    secondary_action_labels: secondaryActionLabels,
    raw_elements: rawElements,
    raw_record_lists: rawRecordLists,
  };
}
