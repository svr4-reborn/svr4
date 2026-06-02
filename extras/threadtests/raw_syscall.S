.section .text

.global test_syscall5
.type test_syscall5, @function
test_syscall5:
	mov 4(%esp), %eax
	mov 8(%esp), %edx
	mov %edx, 4(%esp)
	mov 12(%esp), %edx
	mov %edx, 8(%esp)
	mov 16(%esp), %edx
	mov %edx, 12(%esp)
	mov 20(%esp), %edx
	mov %edx, 16(%esp)
	mov 24(%esp), %edx
	mov %edx, 20(%esp)
	lcall $0x7, $0
	setc %dl
	movzbl %dl, %edx
	ret

.section .note.GNU-stack,"",%progbits