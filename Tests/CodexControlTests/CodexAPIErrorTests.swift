import XCTest
@testable import CodexControl

final class CodexAPIErrorTests: XCTestCase {
    func testServerEOFErrorUsesReadableMessage() {
        let error = CodexAPIError.serverError(
            502,
            "<urlopen error EOF occurred in violation of protocol (_ssl.c:1129)>")

        XCTAssertEqual(
            error.localizedDescription,
            "Codex usage API is temporarily unavailable (502): the upstream connection closed before the response finished. Try again in a moment.")
    }

    func testTransientServerErrorPreservesExistingSnapshot() {
        XCTAssertTrue(CodexAPIError.serverError(502, nil).preservesExistingSnapshot)
        XCTAssertTrue(CodexAPIError.network("connection lost").preservesExistingSnapshot)
        XCTAssertFalse(CodexAPIError.unauthorized.preservesExistingSnapshot)
    }
}
