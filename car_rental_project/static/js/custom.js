document.addEventListener("DOMContentLoaded", function () {
    console.log("Car Rental Project Loaded!");
});

// custom.js
function togglePaymentFields() {
    const paymentMethod = document.getElementById("payment_method").value;
    document.getElementById("card_details").style.display = (paymentMethod === "credit" || paymentMethod === "debit") ? "block" : "none";
    document.getElementById("account_details").style.display = paymentMethod === "account" ? "block" : "none";
}
