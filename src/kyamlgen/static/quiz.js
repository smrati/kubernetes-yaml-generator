/*
 * The quiz.
 *
 * The questions are rendered by the server; this only handles the reveal.  The answer
 * index is on each question as data-answer, so the verdict, the explanation and the
 * score are all computed here.
 */
(function () {
  "use strict";

  function wireQuiz(root) {
    const questions = root.querySelectorAll(".question");
    const progress = root.querySelector("[data-progress]");
    const summary = root.querySelector("[data-summary]");
    const reset = root.querySelector("[data-reset]");
    let answered = 0;
    let correct = 0;

    function update() {
      if (progress) {
        progress.textContent =
          answered + " of " + questions.length + " answered";
      }
      if (summary) {
        if (answered === questions.length && questions.length > 0) {
          summary.hidden = false;
          summary.textContent =
            correct + " of " + questions.length + " correct.";
          summary.className =
            "quiz-summary " + (correct === questions.length ? "is-perfect" : "");
        } else {
          summary.hidden = true;
        }
      }
      if (reset) reset.hidden = answered === 0;
    }

    questions.forEach(function (question) {
      const answer = Number(question.dataset.answer);
      const inputs = question.querySelectorAll('input[type="radio"]');
      const explanation = question.querySelector(".answer");

      inputs.forEach(function (input) {
        input.addEventListener("change", function () {
          if (question.dataset.done === "1") return;
          question.dataset.done = "1";
          answered += 1;

          const chosen = Number(input.value);
          const right = chosen === answer;
          if (right) correct += 1;

          question.classList.add(right ? "is-correct" : "is-wrong");
          input.closest(".option").classList.add(right ? "is-correct" : "is-wrong");
          if (!right) {
            // Mark the right one too, so the learner can see what it was.
            const correctInput = inputs[answer];
            if (correctInput) {
              correctInput.closest(".option").classList.add("is-correct");
              correctInput.disabled = true;
            }
          }

          const verdict = question.querySelector(".verdict");
          if (verdict) {
            verdict.textContent = right ? "Correct" : "Not quite";
            verdict.className = "verdict " + (right ? "is-correct" : "is-wrong");
          }
          if (explanation) explanation.hidden = false;
          update();
        });
      });
    });

    if (reset) {
      reset.addEventListener("click", function () {
        answered = 0;
        correct = 0;
        questions.forEach(function (question) {
          question.dataset.done = "0";
          question.classList.remove("is-correct", "is-wrong");
          question.querySelectorAll(".option").forEach(function (option) {
            option.classList.remove("is-correct", "is-wrong");
          });
          question.querySelectorAll('input[type="radio"]').forEach(function (input) {
            input.checked = false;
            input.disabled = false;
          });
          const explanation = question.querySelector(".answer");
          if (explanation) explanation.hidden = true;
          const verdict = question.querySelector(".verdict");
          if (verdict) {
            verdict.textContent = "";
            verdict.className = "verdict";
          }
        });
        update();
      });
    }

    update();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".quiz").forEach(wireQuiz);
  });
})();
